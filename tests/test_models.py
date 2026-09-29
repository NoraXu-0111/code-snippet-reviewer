import asyncio
import shutil
from contextlib import closing
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import PROJECT_ROOT, Settings
from backend.contracts import ReviewOutput
from backend.database import open_database
from backend.discussion_provider import DiscussionFailure
from test_discussions import FakeDiscussion, settled, setup
from test_reviews import FINDING, FakeReviewer, create, finish


def fake_sdk(monkeypatch):
    calls = []
    control = {'fail_reply': False}

    class Client:
        def __init__(self, **kwargs): self.responses = self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def parse(self, **kwargs):
            calls.append(('review', kwargs['model']))
            await asyncio.sleep(.02)
            return SimpleNamespace(status='completed', output=[], output_parsed=ReviewOutput.model_validate({'findings': [FINDING]}))
        async def create(self, **kwargs):
            calls.append(('discussion', kwargs['model']))
            if control['fail_reply']:
                control['fail_reply'] = False
                raise DiscussionFailure('Simulated failure')
            return SimpleNamespace(status='completed', output=[], output_text='Answer from ' + kwargs['model'])

    monkeypatch.setattr('backend.reviewer.AsyncOpenAI', Client)
    monkeypatch.setattr('backend.discussion_provider.AsyncOpenAI', Client)
    return calls, control


@pytest.mark.parametrize('default', ['gpt-4.1-mini', 'gpt-4.1-2025-04-14'])
def test_catalog_and_configured_default(tmp_path, default):
    settings = Settings(database_path=tmp_path/'test.db', openai_model=default, openai_api_key=None)
    with TestClient(create_app(settings, reviewer=FakeReviewer())) as client:
        catalog = client.get('/api/models').json()
        assert set(catalog) == {'provider', 'defaultModel', 'models'}
        assert catalog['provider'] == 'openai' and catalog['defaultModel'] == default
        assert {'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano', default} <= {item['id'] for item in catalog['models']}
        snippet = create(client)
        run = client.post(f'/api/snippets/{snippet}/reviews', json={'clientRequestId': str(uuid4())}).json()
        assert finish(client, run['id'])['review']['model'] == default


def test_selected_models_reach_adapters_history_and_traces_without_cross_talk(tmp_path, monkeypatch):
    calls, _ = fake_sdk(monkeypatch)
    settings = Settings(database_path=tmp_path/'test.db', openai_api_key='synthetic-test-key')
    with TestClient(create_app(settings)) as client:
        runs = []
        for model in ('gpt-4.1', 'gpt-4.1-nano'):
            snippet = create(client)
            payload = {'clientRequestId': str(uuid4()), 'model': model}
            url = f'/api/snippets/{snippet}/reviews'
            result = client.post(url, json=payload)
            assert result.status_code == 202
            runs.append((snippet, result.json()['id'], model, payload))
        for snippet, id, model, payload in runs:
            result = finish(client, id)
            assert result['review']['model'] == model
            assert client.get(f'/api/snippets/{snippet}').json()['latestReview']['model'] == model
            url = f'/api/snippets/{snippet}/reviews'
            assert client.get(url).json()['reviews'][0]['model'] == model
            assert client.post(url, json=payload).status_code == 200
            assert client.post(url, json={**payload, 'model': 'gpt-4.1-mini'}).status_code == 409
        finding = result['findings'][0]['id']
        url = f'/api/findings/{finding}/discussion'
        payload = {'clientRequestId': str(uuid4()), 'message': 'Explain', 'model': 'gpt-4.1'}
        assert client.post(url, json=payload).status_code == 202
        turn = settled(client, finding)[0]
        assert turn['model'] == 'gpt-4.1' and turn['assistantMessage'] == 'Answer from gpt-4.1'
        assert client.post(url, json=payload).status_code == 200
        assert client.post(url, json={**payload, 'model': 'gpt-4.1-nano'}).status_code == 409
    assert sorted(calls) == sorted([('review', 'gpt-4.1'), ('review', 'gpt-4.1-nano'), ('discussion', 'gpt-4.1')])
    with closing(open_database(settings.database_path)) as db:
        spans = db.execute('SELECT subject_id, model FROM model_calls').fetchall()
        assert {(row['subject_id'], row['model']) for row in spans} == {(id, model) for _, id, model, _ in runs} | {(turn['id'], 'gpt-4.1')}
    assert settings.openai_model == 'gpt-4.1-mini'


def test_recovery_and_retry_retain_model_after_default_changes(tmp_path, monkeypatch):
    calls, control = fake_sdk(monkeypatch)
    settings = Settings(database_path=tmp_path/'test.db', openai_api_key='synthetic-test-key')
    request_id, question_id = str(uuid4()), str(uuid4())
    with TestClient(create_app(settings)) as client:
        snippet = create(client)
        url = f'/api/snippets/{snippet}/reviews'
        # Legacy clients omit model; the server still fixes the effective default on creation.
        run = client.post(url, json={'clientRequestId': request_id}).json()
        result = finish(client, run['id'])
        finding = result['findings'][0]['id']
        question = {'clientRequestId': question_id, 'message': 'Explain', 'model': 'gpt-4.1'}
        control['fail_reply'] = True
        reply_url = f'/api/findings/{finding}/discussion'
        client.post(reply_url, json=question)
        failed = settled(client, finding)[0]
        assert failed['status'] == 'failed' and failed['model'] == 'gpt-4.1'
    changed = settings.model_copy(update={'openai_model': 'gpt-4.1-nano', 'openai_api_key': None})
    with TestClient(create_app(changed)) as client:
        replay = client.post(url, json={'clientRequestId': request_id})
        assert replay.status_code == 200 and replay.json()['model'] == 'gpt-4.1-mini'
        replay = client.post(reply_url, json=question)
        assert replay.status_code == 200 and replay.json()['model'] == 'gpt-4.1'
    with TestClient(create_app(settings.model_copy(update={'openai_model': 'gpt-4.1-nano'}))) as client:
        retried = client.post(f"/api/discussion-turns/{failed['id']}/retry", json={'attempt': 1})
        assert retried.status_code == 202
        assert settled(client, finding)[0]['model'] == 'gpt-4.1'
        new_run = client.post(url, json={'clientRequestId': str(uuid4())}).json()
        assert finish(client, new_run['id'])['review']['model'] == 'gpt-4.1-nano'
    assert calls == [('review', 'gpt-4.1-mini'), ('discussion', 'gpt-4.1'), ('discussion', 'gpt-4.1'), ('review', 'gpt-4.1-nano')]
    with closing(open_database(settings.database_path)) as db:
        retry_span = db.execute('SELECT model FROM model_calls WHERE subject_id=? AND attempt=2', (failed['id'],)).fetchone()
        assert retry_span['model'] == 'gpt-4.1'


def test_invalid_models_do_not_schedule_work(tmp_path):
    reviewer, discussion = FakeReviewer(), FakeDiscussion()
    with TestClient(create_app(Settings(database_path=tmp_path/'test.db'), reviewer=reviewer, discussion_provider=discussion)) as client:
        snippet, _, finding = setup(client)
        for model in ('not-an-allowed-model', '', 123):
            payload = {'clientRequestId': str(uuid4()), 'model': model}
            assert client.post(f'/api/snippets/{snippet}/reviews', json=payload).status_code == 400
            assert client.post(f'/api/findings/{finding}/discussion', json={**payload, 'message': 'Why?'}).status_code == 400
        assert reviewer.calls == 1 and discussion.calls == []
        assert len(client.get(f'/api/snippets/{snippet}/reviews').json()['reviews']) == 1


def test_model_migration_uses_trace_evidence_only(tmp_path, monkeypatch):
    import backend.database as database
    from test_foundation import insert_run, insert_snippet, NOW
    old_root = tmp_path/'old'
    (old_root/'migrations').mkdir(parents=True)
    for migration in (PROJECT_ROOT/'migrations').glob('00[1-6]_*.sql'):
        shutil.copyfile(migration, old_root/'migrations'/migration.name)
    path = tmp_path/'old.db'
    with monkeypatch.context() as patch:
        patch.setattr(database, 'PROJECT_ROOT', old_root)
        with closing(open_database(path)) as db:
            snippet = insert_snippet(db)
            known = insert_run(db, snippet)
            unknown = insert_run(db, insert_snippet(db))
            db.execute("INSERT INTO model_calls (id, operation, subject_id, attempt, model, prompt_version, started_at, status) VALUES (?, 'review', ?, 1, 'gpt-4.1', 'review-v2', ?, 'running')", (str(uuid4()), known, NOW))
            before = [dict(row) for row in db.execute('SELECT * FROM review_runs ORDER BY rowid')]
    with closing(open_database(path)) as db:
        after = [dict(row) for row in db.execute('SELECT * FROM review_runs ORDER BY rowid')]
        assert [row.pop('model') for row in after] == ['gpt-4.1', None]
        assert after == before
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
