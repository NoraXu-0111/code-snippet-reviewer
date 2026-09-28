import asyncio
from contextlib import closing
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.database import open_database
from backend.tracing import record_response, recover_traces, trace_subject, traced


def rows(path):
    with closing(open_database(path)) as db:
        return [dict(row) for row in db.execute('SELECT * FROM model_calls ORDER BY rowid')]


class Provider:
    prompt_version = 'test-v1'
    def __init__(self, path):
        self.settings = Settings(database_path=path, openai_api_key='SECRET-KEY')

    @traced('review')
    async def call(self, error=False, delay=0):
        await asyncio.sleep(delay)
        record_response(SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20), _request_id='req_test', id='resp_test'))
        if error:
            raise ValueError('SECRET CODE AND EXCEPTION TEXT')
        return 'PRIVATE ANSWER'


def test_trace_records_metadata_not_content_and_context_isolated(tmp_path):
    path=tmp_path/'test.db'; open_database(path).close(); provider=Provider(path)
    async def run():
        async def one(subject, attempt):
            with trace_subject(subject, attempt):
                await provider.call(delay=.01)
        await asyncio.gather(one('review-a',1),one('review-b',2))
        await provider.call()  # Unscoped calls do not write to an implicit DB.
    asyncio.run(run())
    saved=rows(path)
    assert len(saved)==2
    assert {(row['subject_id'],row['attempt']) for row in saved}=={('review-a',1),('review-b',2)}
    for row in saved:
        assert row['status']=='succeeded' and row['duration_ms'] >= 0
        assert row['input_tokens']==100 and row['output_tokens']==20
        assert row['request_id']=='req_test' and row['prompt_version']=='test-v1'
    assert 'PRIVATE' not in str(saved) and 'SECRET' not in str(saved)


def test_failed_cancelled_interrupted_and_observability_failure(tmp_path):
    path=tmp_path/'test.db'; open_database(path).close(); provider=Provider(path)
    async def run():
        with trace_subject('failed'):
            with pytest.raises(ValueError):
                await provider.call(error=True)
        with trace_subject('cancelled'):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(.01):
                    await provider.call(delay=10)
    asyncio.run(run())
    saved=rows(path)
    assert [row['status'] for row in saved]==['failed','cancelled']
    assert saved[0]['error_type']=='ValueError' and 'SECRET' not in str(saved)
    with closing(open_database(path)) as db:
        db.execute("UPDATE model_calls SET status='running', finished_at=NULL WHERE subject_id='failed'")
    recover_traces(path)
    assert rows(path)[0]['status']=='interrupted'
    # Missing schema simulates tracing storage failure without breaking review output.
    provider.settings=Settings(database_path=tmp_path/'missing.db')
    async def unavailable():
        with trace_subject('no-schema'):
            assert await provider.call()=='PRIVATE ANSWER'
    asyncio.run(unavailable())


def test_real_provider_adapters_correlate_api_review_and_discussion(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.contracts import ReviewOutput
    from backend.reviewer import OpenAIReviewer
    from test_openai_reviewer import install_fake as review_client
    from test_openai_discussion import install_fake as discussion_client
    from test_reviews import FINDING, create, finish, start
    from test_discussions import ask, settled

    review_client(monkeypatch, SimpleNamespace(status='completed', output=[], output_parsed=ReviewOutput.model_validate({'findings':[FINDING]})))
    discussion_client(monkeypatch, SimpleNamespace(status='completed', output=[], output_text='A safe answer'))
    settings=Settings(database_path=tmp_path/'api.db',openai_api_key='synthetic-test-key')
    with TestClient(create_app(settings)) as client:
        snippet=create(client)
        run=finish(client,start(client,snippet))
        finding=run['findings'][0]['id']
        ask(client,finding)
        turn=settled(client,finding)[0]
    saved=rows(settings.database_path)
    assert [(row['operation'],row['subject_id'],row['attempt'],row['status']) for row in saved]==[
        ('review',run['review']['id'],1,'succeeded'),('discussion',turn['id'],1,'succeeded')]
    assert saved[0]['prompt_version']==OpenAIReviewer.prompt_version
    assert saved[1]['prompt_version']=='discussion-v1'
