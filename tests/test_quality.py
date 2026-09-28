import copy
import json
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import quality
from backend.app import create_app
from backend.config import PROJECT_ROOT, Settings
from backend.database import open_database


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(database_path=tmp_path/'quality.db', openai_api_key=None)
    with TestClient(create_app(settings)) as client:
        yield client, settings


def start(client):
    catalog = client.get('/api/quality/catalog').json()
    source = next(source for source in catalog['sources'] if source['label'] == 'candidate-v2')
    result = client.post('/api/quality/sessions', json={'sourceId': source['id'], 'reviewer': 'Human reviewer'})
    assert result.status_code == 200
    return result.json()


def payload(case, complete=False):
    return {'revision': 0, 'status': 'completed' if complete else 'draft',
            'independentNotes': 'Independent code inspection with a minimal reproducer.',
            'contractNotes': 'No caller contract is supplied; do not assume extra requirements.',
            'referenceVerdict': 'uncertain', 'referenceNotes': 'Missing requirements prevent approval.',
            'proposedReference': '',
            'findings': [{'runIndex': run['index'], 'findingIndex': index,
                          'verdict': 'uncertain', 'location': 'good', 'severity': 'uncertain',
                          'fix': 'uncertain' if finding['suggestedFix'] else 'not_applicable',
                          'notes': 'Behavior depends on an unspecified caller contract.'}
                         for run in case['runs'] for index, finding in enumerate(run['findings'])],
            'coverage': [{'runIndex': run['index'], 'verdict': 'uncertain' if run['status'] == 'succeeded' else 'failed',
                          'notes': 'Cannot establish full coverage without a contract.'} for run in case['runs']]}


def url(session, case):
    return f"/api/quality/sessions/{session['id']}/cases/{case['id']}"


def test_round_trip_history_restart_export_and_no_model_calls(workspace):
    client, settings = workspace
    session = start(client)
    assert start(client)['id'] == session['id']
    case = session['cases'][0]
    annotation = payload(case)
    first = client.put(url(session, case), json=annotation)
    assert first.status_code == 200
    assert first.json()['revision'] == 1
    annotation.update(revision=1, status='completed')
    second = client.put(url(session, case), json=annotation)
    assert second.status_code == 200
    export = client.get(f"/api/quality/sessions/{session['id']}/export")
    assert 'attachment' in export.headers['content-disposition']
    data = export.json()
    assert [item['revision'] for item in data['history']] == [1, 2]
    assert data['annotations'][case['id']]['referenceVerdict'] == 'uncertain'
    assert data['snapshot']['cases'][0]['code'] == case['code']
    assert data['snapshot']['originalReport']['promptVersion'] == 'review-v2'
    assert client.get('/api/quality/catalog').json()['sessions'][0]['completed'] == 1
    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get(f"/api/quality/sessions/{session['id']}").json()
        assert restored['annotations'][case['id']]['revision'] == 2
    with closing(open_database(settings.database_path)) as db:
        assert db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM snippets').fetchone()[0] == 0


def test_stale_updates_are_rejected_and_never_overwrite(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    draft = payload(case)
    assert client.put(url(session, case), json=draft).status_code == 200
    draft['independentNotes'] = 'A stale tab overwriting a newer judgment'
    assert client.put(url(session, case), json=draft).status_code == 409
    stored = client.get(f"/api/quality/sessions/{session['id']}").json()['annotations'][case['id']]
    assert stored['revision'] == 1
    assert stored['independentNotes'] != draft['independentNotes']


def test_completion_requires_full_evidence_but_drafts_allow_partial(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    complete = payload(case, complete=True)
    mutations = [ {'independentNotes': ' '}, {'referenceVerdict': 'pending'},
                  {'findings': []}, {'coverage': []}, {'referenceNotes': ''} ]
    for change in mutations:
        result = client.put(url(session, case), json={**complete, **change})
        assert result.status_code == 400, result.text
    missing = copy.deepcopy(complete); missing['findings'][0]['fix'] = 'pending'
    assert client.put(url(session, case), json=missing).status_code == 400
    assert client.put(url(session, case), json={'revision': 0}).status_code == 200
    complete['revision'] = 1
    assert client.put(url(session, case), json=complete).status_code == 200


def test_annotation_identity_validation_and_missing_resources(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    draft = payload(case)
    for bad in [draft['findings'] * 2, [{**draft['findings'][0], 'runIndex': 100000}],
                [{**draft['findings'][0], 'findingIndex': 100000}]]:
        assert client.put(url(session, case), json={**draft, 'findings': bad}).status_code == 400
    assert client.put(url(session, case), json={**draft, 'coverage': draft['coverage']*2}).status_code == 400
    assert client.put(url(session, case), json={**draft, 'status': 'gold'}).status_code == 400
    assert client.put(url(session, {'id': 'not-in-session'}), json=draft).status_code == 404
    assert client.get(f'/api/quality/sessions/{uuid4()}').status_code == 404
    assert client.post('/api/quality/sessions', json={'sourceId': '../../.env', 'reviewer': 'x'}).status_code == 404
    assert client.post('/api/quality/sessions', json={'sourceId': session['source']['id'], 'reviewer': ' '}).status_code == 400


def test_source_hash_validation_and_frozen_snapshots(workspace, tmp_path, monkeypatch):
    client, _ = workspace
    session = start(client)
    original = client.get(f"/api/quality/sessions/{session['id']}").json()
    dataset = tmp_path/'dataset.json'; dataset.write_text('[]')
    with pytest.raises(ValueError, match='does not match'):
        quality.load_source(PROJECT_ROOT/'evals/reports/candidate-v2.json', dataset, 'mismatch')
    monkeypatch.setattr(quality, 'discover_sources', lambda: ({}, ['candidate-v2']))
    assert client.get(f"/api/quality/sessions/{session['id']}").json() == original
    assert client.get('/api/quality/catalog').json()['sessions'][0]['id'] == session['id']


def test_zero_finding_and_failed_runs_require_coverage(workspace, tmp_path, monkeypatch):
    client, _ = workspace
    session = start(client)
    clean = next(case for case in session['cases'] if case['id'] == 'safe-average')
    assert all(not run['findings'] for run in clean['runs'])
    assessment = payload(clean, complete=True)
    assessment['coverage'][0]['verdict'] = 'pending'
    assert client.put(url(session, clean), json=assessment).status_code == 400
    assessment['coverage'][0]['verdict'] = 'complete'
    assert client.put(url(session, clean), json=assessment).status_code == 200
    report = json.loads((PROJECT_ROOT/'evals/reports/candidate-v2.json').read_text())
    report['rows'] = [{**report['rows'][0], 'status': 'failed', 'errorType': 'TimeoutError'}]
    del report['rows'][0]['output']
    path = tmp_path/'failed.json'; path.write_text(json.dumps(report))
    snapshot = quality.load_source(path, PROJECT_ROOT/'evals/cases.json', 'failed')
    monkeypatch.setattr(quality, 'discover_sources', lambda: ({snapshot['source']['id']: snapshot}, []))
    session = client.post('/api/quality/sessions', json={'sourceId': snapshot['source']['id'], 'reviewer': 'x'}).json()
    case = session['cases'][0]; assessment = payload(case, complete=True)
    assessment['coverage'][0]['verdict'] = 'complete'
    assert client.put(url(session, case), json=assessment).status_code == 400
    assessment['coverage'][0]['verdict'] = 'failed'
    assert client.put(url(session, case), json=assessment).status_code == 200


def choices_only(case):
    assessment = payload(case, complete=True)
    assessment.update(independentNotes='', contractNotes='', referenceNotes='',
                      independentVerdict='uncertain', contractClarity='missing',
                      referenceVerdict='needs_changes', referenceReason='wrong_details')
    for finding in assessment['findings']:
        finding.update(notes='', reason='missing_context')
    for coverage in assessment['coverage']:
        coverage['notes'] = ''
    return assessment


def test_choices_only_completion_and_export_preserve_empty_notes(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    assessment = choices_only(case)
    result = client.put(url(session, case), json=assessment)
    assert result.status_code == 200, result.text
    assert result.json()['proposedReference'] == ''  # Correction can be deferred for discussion.
    exported = client.get(f"/api/quality/sessions/{session['id']}/export").json()
    saved = exported['annotations'][case['id']]
    assert saved['referenceReason'] == 'wrong_details'
    assert saved['independentVerdict'] == 'uncertain'
    assert saved['contractClarity'] == 'missing'
    assert saved['independentNotes'] == saved['referenceNotes'] == saved['contractNotes'] == ''
    assert all(f['notes'] == '' and f['reason'] == 'missing_context' for f in saved['findings'])
    assert all(c['notes'] == '' for c in saved['coverage'])


def test_blank_choices_cannot_be_completed_without_legacy_notes(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    assessment = choices_only(case)
    for field in ('independentVerdict', 'contractClarity', 'referenceReason'):
        assert client.put(url(session, case), json={**assessment, field: 'pending'}).status_code == 400
    missing = copy.deepcopy(assessment)
    missing['findings'][0]['reason'] = 'pending'
    assert client.put(url(session, case), json=missing).status_code == 400
    missing['status'] = 'draft'
    assert client.put(url(session, case), json=missing).status_code == 200


def test_reason_codes_must_be_known_and_match_the_judgment(workspace):
    client, _ = workspace
    session = start(client); case = session['cases'][0]
    assessment = choices_only(case)
    assert client.put(url(session, case), json={**assessment, 'referenceReason': 'supported'}).status_code == 400
    assert client.put(url(session, case), json={**assessment, 'referenceReason': 'invented'}).status_code == 400
    assessment['findings'][0]['reason'] = 'duplicate'
    assert client.put(url(session, case), json=assessment).status_code == 400
