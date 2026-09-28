"""Local human annotations. Snapshots and append-only revisions never alter eval labels."""
import hashlib
import json
from contextlib import closing
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from .config import PROJECT_ROOT
from .contracts import Contract, FindingContent, parse_review_output
from .database import open_database

Verdict = Literal['pending', 'correct', 'incorrect', 'uncertain', 'duplicate']
Rating = Literal['pending', 'good', 'problem', 'uncertain', 'not_applicable']


class FindingAnnotation(Contract):
    run_index: int = Field(ge=0, strict=True)
    finding_index: int = Field(ge=0, strict=True)
    verdict: Verdict = 'pending'
    reason: Literal['pending', 'supported', 'unsupported_assumption', 'contradicts_code', 'not_actionable', 'duplicate', 'missing_context', 'needs_verification'] = 'pending'
    location: Rating = 'pending'
    severity: Rating = 'pending'
    fix: Rating = 'pending'
    notes: str = Field(default='', max_length=8000)


class CoverageAnnotation(Contract):
    run_index: int = Field(ge=0, strict=True)
    verdict: Literal['pending', 'complete', 'missed', 'uncertain', 'failed'] = 'pending'
    notes: str = Field(default='', max_length=8000)


class AnnotationInput(Contract):
    revision: int = Field(ge=0, strict=True)
    status: Literal['draft', 'completed'] = 'draft'
    independent_verdict: Literal['pending', 'issue_found', 'no_issue', 'uncertain'] = 'pending'
    contract_clarity: Literal['pending', 'sufficient', 'missing', 'uncertain'] = 'pending'
    reference_reason: Literal['pending', 'supported', 'false_positive', 'missing_issue', 'wrong_details', 'missing_context', 'needs_verification'] = 'pending'
    independent_notes: str = Field(default='', max_length=8000)
    contract_notes: str = Field(default='', max_length=8000)
    reference_verdict: Literal['pending', 'approved', 'needs_changes', 'uncertain'] = 'pending'
    reference_notes: str = Field(default='', max_length=8000)
    proposed_reference: str = Field(default='', max_length=8000)
    findings: list[FindingAnnotation] = Field(default_factory=list, max_length=2000)
    coverage: list[CoverageAnnotation] = Field(default_factory=list, max_length=100)


class SavedAnnotation(AnnotationInput):
    saved_at: str


class QualityRun(Contract):
    index: int
    repeat: int
    status: Literal['succeeded', 'failed']
    findings: list[FindingContent]
    error_type: str | None = None


class QualityCase(Contract):
    id: str
    language: str
    code: str
    expected: list[dict]
    notes: str
    runs: list[QualityRun]


class SourceInfo(Contract):
    id: str
    label: str
    model: str
    prompt_version: str
    case_count: int
    run_count: int


class SessionInfo(Contract):
    id: str
    reviewer: str
    label: str
    created_at: str
    completed: int
    total: int


class Catalog(Contract):
    sources: list[SourceInfo]
    sessions: list[SessionInfo]
    unavailable: list[str]


class NewSession(Contract):
    source_id: str = Field(min_length=1, max_length=64)
    reviewer: str = Field(min_length=1, max_length=80)

    @field_validator('reviewer', mode='before')
    @classmethod
    def trim_reviewer(cls, value):
        return value.strip() if isinstance(value, str) else value


class SessionDetail(Contract):
    id: str
    reviewer: str
    created_at: str
    source: SourceInfo
    dataset_sha256: str
    report_sha256: str
    cases: list[QualityCase]
    annotations: dict[str, SavedAnnotation]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_source(report_path, dataset_path, label):
    report_bytes, dataset_bytes = report_path.read_bytes(), dataset_path.read_bytes()
    report, dataset = json.loads(report_bytes), json.loads(dataset_bytes)
    if report['datasetSha256'] != digest(dataset_bytes):
        raise ValueError('Dataset does not match the report; original snapshot required')
    by_id = {case['id']: case for case in dataset}
    if len(by_id) != len(dataset):
        raise ValueError('Duplicate case IDs')
    grouped = {}
    for index, row in enumerate(report['rows']):
        case = by_id[row['caseId']]
        if row['status'] not in ('succeeded', 'failed'):
            raise ValueError('Unsupported run status')
        findings = parse_review_output(row['output'], case['code']).findings if row['status'] == 'succeeded' else []
        grouped.setdefault(case['id'], []).append(QualityRun(
            index=index, repeat=row['repeat'], status=row['status'], findings=findings,
            error_type=row.get('errorType')))
    cases = [QualityCase(id=case['id'], language=case['language'], code=case['code'],
                         expected=case['expected'], notes=case.get('notes', ''), runs=grouped[case['id']])
             for case in dataset if case['id'] in grouped]
    if not cases:
        raise ValueError('Empty report')
    source_id = digest(report_bytes + b'\0' + dataset_bytes)
    source = SourceInfo(id=source_id, label=label, model=report['model'],
                        prompt_version=report['promptVersion'], case_count=len(cases), run_count=len(report['rows']))
    return {'source': source.model_dump(mode='json', by_alias=True),
            'datasetSha256': digest(dataset_bytes), 'reportSha256': digest(report_bytes),
            'cases': [case.model_dump(mode='json', by_alias=True) for case in cases],
            'originalDataset': dataset, 'originalReport': report}


def discover_sources():
    candidates = [(PROJECT_ROOT/'evals/reports'/f'{name}.json', PROJECT_ROOT/'evals/cases.json', name)
                  for name in ('candidate-v2', 'baseline-v1', 'candidate-v3')]
    candidates += [(path, path.parent/'dataset.json', f'local/{path.parent.name}')
                   for path in sorted((PROJECT_ROOT/'work/evals').glob('*/results.json'), reverse=True)]
    sources, unavailable = {}, []
    for report, dataset, label in candidates:
        try:
            snapshot = load_source(report, dataset, label)
            sources.setdefault(snapshot['source']['id'], snapshot)
        except (OSError, ValueError, KeyError, TypeError):
            unavailable.append(label)
    return sources, unavailable


def saved_annotations(db, session_id):
    rows = db.execute('SELECT * FROM quality_annotations WHERE session_id=? ORDER BY revision', (session_id,))
    return {row['case_id']: {**json.loads(row['payload']), 'revision': row['revision'], 'savedAt': row['saved_at']} for row in rows}


def get_session(db, session_id):
    row = db.execute('SELECT * FROM quality_sessions WHERE id=?', (str(session_id),)).fetchone()
    if row is None:
        raise HTTPException(404, 'Annotation session not found')
    return row, json.loads(row['snapshot'])


def detail(db, session_id):
    row, snapshot = get_session(db, session_id)
    return SessionDetail(id=row['id'], reviewer=row['reviewer'], created_at=row['created_at'],
                         source=snapshot['source'], dataset_sha256=snapshot['datasetSha256'],
                         report_sha256=snapshot['reportSha256'], cases=snapshot['cases'],
                         annotations=saved_annotations(db, str(session_id)))


def validate_annotation(case, payload):
    runs = {run['index']: run for run in case['runs']}
    expected_keys = {(run['index'], i) for run in case['runs'] for i in range(len(run['findings']))}
    keys = [(finding.run_index, finding.finding_index) for finding in payload.findings]
    coverage_keys = [item.run_index for item in payload.coverage]
    if len(keys) != len(set(keys)) or set(keys) - expected_keys:
        raise HTTPException(400, 'Finding annotations must refer to unique findings in this case')
    if len(coverage_keys) != len(set(coverage_keys)) or set(coverage_keys) - runs.keys():
        raise HTTPException(400, 'Coverage annotations must refer to unique runs in this case')
    for item in payload.coverage:
        if ((runs[item.run_index]['status'] == 'failed' and item.verdict not in ('pending', 'failed'))
                or (runs[item.run_index]['status'] == 'succeeded' and item.verdict == 'failed')):
            raise HTTPException(400, 'Failed calls cannot be marked as successful coverage')
    if payload.status != 'completed':
        return
    # Older text-only annotations remain valid. New assessments can use choices only.
    if ((payload.independent_verdict == 'pending' and not payload.independent_notes.strip())
            or (payload.contract_clarity == 'pending' and not payload.contract_notes.strip())
            or payload.reference_verdict == 'pending'
            or (payload.reference_reason == 'pending' and not payload.reference_notes.strip())):
        raise HTTPException(400, 'Choose your code assessment, input clarity, reference verdict and reason; written notes are optional')
    reference_reasons = {
        'approved': {'supported'},
        'needs_changes': {'false_positive', 'missing_issue', 'wrong_details'},
        'uncertain': {'missing_context', 'needs_verification'},
    }
    if payload.reference_reason != 'pending' and payload.reference_reason not in reference_reasons[payload.reference_verdict]:
        raise HTTPException(400, 'Reference reason must agree with the reference verdict')
    if set(keys) != expected_keys or set(coverage_keys) != runs.keys():
        raise HTTPException(400, 'Assess every finding and every run before completing this case')
    for finding in payload.findings:
        if ('pending' in (finding.verdict, finding.location, finding.severity, finding.fix)
                or (finding.reason == 'pending' and not finding.notes.strip())):
            raise HTTPException(400, 'Every finding needs a verdict, three ratings and a reason; written notes are optional')
        finding_reasons = {
            'correct': {'supported'},
            'incorrect': {'unsupported_assumption', 'contradicts_code', 'not_actionable'},
            'duplicate': {'duplicate'},
            'uncertain': {'missing_context', 'needs_verification'},
        }
        if finding.reason != 'pending' and finding.reason not in finding_reasons[finding.verdict]:
            raise HTTPException(400, 'Finding reason must agree with the finding verdict')
        if not runs[finding.run_index]['findings'][finding.finding_index].get('suggestedFix') and finding.fix != 'not_applicable':
            raise HTTPException(400, 'A finding without a suggested fix must use Not applicable for fix quality')
    if any(item.verdict == 'pending' for item in payload.coverage):
        raise HTTPException(400, 'Choose coverage for every run, including runs with no findings; written notes are optional')


def quality_router(settings):
    router = APIRouter(prefix='/api/quality', tags=['Human evaluation'])

    @router.get('/catalog', response_model=Catalog)
    def catalog():
        sources, unavailable = discover_sources()
        sessions = []
        with closing(open_database(settings.database_path, migrate=False)) as db:
            for row in db.execute('SELECT * FROM quality_sessions ORDER BY created_at DESC'):
                snapshot = json.loads(row['snapshot'])
                annotations = saved_annotations(db, row['id'])
                sessions.append(SessionInfo(id=row['id'], reviewer=row['reviewer'], label=snapshot['source']['label'],
                                            created_at=row['created_at'], total=len(snapshot['cases']),
                                            completed=sum(a['status'] == 'completed' for a in annotations.values())))
        return Catalog(sources=[s['source'] for s in sources.values()], sessions=sessions, unavailable=unavailable)

    @router.post('/sessions', response_model=SessionDetail)
    def create_session(payload: NewSession):
        sources, _ = discover_sources()
        snapshot = sources.get(payload.source_id)
        if snapshot is None:
            raise HTTPException(404, 'Evaluation source unavailable; reload the catalog')
        with closing(open_database(settings.database_path, migrate=False)) as db:
            db.execute('INSERT OR IGNORE INTO quality_sessions VALUES (?,?,?,?,?)',
                       (str(uuid4()), payload.source_id, payload.reviewer, datetime.now(timezone.utc).isoformat(), json.dumps(snapshot)))
            row = db.execute('SELECT id FROM quality_sessions WHERE source_id=? AND reviewer=?', (payload.source_id, payload.reviewer)).fetchone()
            return detail(db, row['id'])

    @router.get('/sessions/{session_id}', response_model=SessionDetail)
    def read_session(session_id: UUID):
        with closing(open_database(settings.database_path, migrate=False)) as db:
            return detail(db, session_id)

    @router.put('/sessions/{session_id}/cases/{case_id}', response_model=SavedAnnotation)
    def save(session_id: UUID, case_id: str, payload: AnnotationInput):
        with closing(open_database(settings.database_path, migrate=False)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                _, snapshot = get_session(db, session_id)
                case = next((c for c in snapshot['cases'] if c['id'] == case_id), None)
                if case is None:
                    raise HTTPException(404, 'Case not in this session')
                validate_annotation(case, payload)
                current = db.execute('SELECT MAX(revision) FROM quality_annotations WHERE session_id=? AND case_id=?', (str(session_id), case_id)).fetchone()[0] or 0
                if payload.revision != current:
                    raise HTTPException(409, 'This case was saved in another tab. Export or copy your draft, then reload the saved version.')
                result = SavedAnnotation(**{**payload.model_dump(), 'revision': current + 1}, saved_at=datetime.now(timezone.utc).isoformat())
                db.execute('INSERT INTO quality_annotations VALUES (?,?,?,?,?)',
                           (str(session_id), case_id, result.revision, result.saved_at, result.model_dump_json(by_alias=True)))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise

    @router.get('/sessions/{session_id}/export')
    def export(session_id: UUID):
        from fastapi.responses import JSONResponse
        with closing(open_database(settings.database_path, migrate=False)) as db:
            db.execute('BEGIN')  # Export history and latest labels from one consistent snapshot.
            row, snapshot = get_session(db, session_id)
            history = [{'caseId': record['case_id'], **json.loads(record['payload'])}
                       for record in db.execute('SELECT * FROM quality_annotations WHERE session_id=? ORDER BY saved_at, case_id, revision', (str(session_id),))]
            content = {'schemaVersion': 1, 'sessionId': str(session_id), 'reviewer': row['reviewer'],
                       'createdAt': row['created_at'], 'exportedAt': datetime.now(timezone.utc).isoformat(),
                       'notice': 'Human annotations over a development set. Completed means assessed, not gold approval. Proposed references do not alter the original dataset. Only saved revisions are exported.',
                       'snapshot': snapshot, 'annotations': saved_annotations(db, str(session_id)), 'history': history}
            return JSONResponse(content, headers={'Content-Disposition': f'attachment; filename="human-review-{session_id}.json"'})

    return router
