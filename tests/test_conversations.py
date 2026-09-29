import shutil
import sqlite3
import time
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import PROJECT_ROOT, Settings
from backend.database import open_database
from backend.discussion_provider import DiscussionFailure
from test_discussions import FakeDiscussion, setup, ask, settled
from test_reviews import FakeReviewer


def new(client, finding, key=None):
    return client.post(f'/api/findings/{finding}/conversations', json={'clientRequestId': key or str(uuid4())})


def send(client, finding, conversation, message='Why?', key=None):
    return client.post(f'/api/findings/{finding}/discussion', json={
        'message': message, 'clientRequestId': key or str(uuid4()), 'conversationId': conversation})


def view(client, finding, conversation):
    result = client.get(f'/api/findings/{finding}/discussion', params={'conversationId': conversation})
    assert result.status_code == 200, result.text
    return result.json()


def finish(client, finding, conversation):
    for _ in range(300):
        result = view(client, finding, conversation)
        if result['turns'] and result['turns'][-1]['status'] in ('succeeded', 'failed'):
            return result['turns'][-1]
        time.sleep(.01)
    pytest.fail('Conversation never finished')


def test_same_finding_conversations_isolate_context_and_survive_restart(tmp_path):
    settings = Settings(database_path=tmp_path/'conversations.db')
    provider = FakeDiscussion()
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=provider)) as client:
        snippet, review, finding = setup(client)
        ask(client, finding, 'Original question'); settled(client, finding)
        created = new(client, finding)
        assert created.status_code == 201
        second = created.json()['id']
        assert view(client, finding, second)['turns'] == []
        assert len(provider.calls) == 1  # Creating a conversation does not call the model.
        send(client, finding, second, 'Fresh start'); finish(client, finding, second)
        assert provider.calls[-1][2] == []
        send(client, finding, second, 'Follow up here'); finish(client, finding, second)
        assert [turn.user_message for turn in provider.calls[-1][2]] == ['Fresh start']
        send(client, finding, finding, 'Resume original'); finish(client, finding, finding)
        assert [turn.user_message for turn in provider.calls[-1][2]] == ['Original question']
        assert str(provider.calls[-1][1].id) == finding
        assert str(provider.calls[-1][0].id) == snippet
        client.patch(f'/api/findings/{finding}', json={'resolution':'dismissed'})
        old = view(client, finding, finding); fresh = view(client, finding, second)
        assert len(old['turns']) == len(fresh['turns']) == 2
        assert len(fresh['conversations']) == 2
    with TestClient(create_app(settings)) as client:
        assert view(client, finding, second) == fresh
        assert view(client, finding, finding) == old
        assert client.get(f'/api/reviews/{review}').json()['findings'][0]['resolution'] == 'dismissed'


def test_creation_is_idempotent_keyless_and_scoped(tmp_path):
    settings = Settings(database_path=tmp_path/'test.db', openai_api_key=None)
    with TestClient(create_app(settings, reviewer=FakeReviewer())) as client:
        _, _, finding = setup(client); _, _, other = setup(client)
        key = str(uuid4())
        first = new(client, finding, key)
        assert first.status_code == 201
        assert new(client, finding, key).status_code == 200
        assert new(client, finding, key).json() == first.json()
        assert new(client, other, key).status_code == 409
        assert new(client, finding, other).status_code == 409
        assert new(client, str(uuid4())).status_code == 404
        assert client.get(f'/api/findings/{other}/discussion?conversationId={key}').status_code == 404
        assert send(client, other, key).status_code == 404
        assert send(client, finding, key).status_code == 503
        assert len(view(client, finding, key)['conversations']) == 2
        assert view(client, finding, key)['turns'] == []


def test_turn_replay_never_moves_to_another_conversation(tmp_path):
    provider = FakeDiscussion()
    with TestClient(create_app(Settings(database_path=tmp_path/'test.db'), reviewer=FakeReviewer(), discussion_provider=provider)) as client:
        _, _, finding = setup(client)
        second = new(client, finding).json()['id']; key = str(uuid4())
        response = send(client, finding, second, key=key)
        finish(client, finding, second)
        replay = send(client, finding, second, key=key)
        assert replay.status_code == 200 and replay.json()['id'] == response.json()['id']
        assert send(client, finding, finding, key=key).status_code == 409
        assert view(client, finding, finding)['turns'] == []
        assert len(provider.calls) == 1


def test_retry_is_latest_in_its_conversation_and_respects_active_finding(tmp_path):
    provider = FakeDiscussion(error=DiscussionFailure('Failed'))
    with TestClient(create_app(Settings(database_path=tmp_path/'test.db'), reviewer=FakeReviewer(), discussion_provider=provider)) as client:
        _, _, finding = setup(client)
        second = new(client, finding).json()['id']
        send(client, finding, finding)
        failed = finish(client, finding, finding)
        provider.error = None; provider.delay = .2
        send(client, finding, second)
        assert view(client, finding, finding)['hasActiveReply'] is True
        assert new(client, finding).status_code == 409
        assert send(client, finding, finding).status_code == 409
        retry_path = f"/api/discussion-turns/{failed['id']}/retry"
        assert client.post(retry_path, json={'attempt': 1}).status_code == 409
        finish(client, finding, second)
        # A newer question in another conversation does not invalidate this retry.
        assert client.post(retry_path, json={'attempt': 1}).status_code == 202
        assert finish(client, finding, finding)['status'] == 'succeeded'
        assert provider.calls[-1][2] == []


def test_migration_preserves_original_turns_and_enforces_finding_ownership(tmp_path, monkeypatch):
    import backend.database as database_module
    from test_foundation import insert_snippet, insert_run, NOW
    old_root = tmp_path/'old'; (old_root/'migrations').mkdir(parents=True)
    for migration in sorted((PROJECT_ROOT/'migrations').glob('00[1-4]_*.sql')):
        shutil.copyfile(migration, old_root/'migrations'/migration.name)
    path = tmp_path/'legacy.db'; finding = str(uuid4()); turn = str(uuid4())
    with monkeypatch.context() as patch:
        patch.setattr(database_module, 'PROJECT_ROOT', old_root)
        with closing(open_database(path)) as db:
            snippet = insert_snippet(db); review = insert_run(db, snippet)
            db.execute("INSERT INTO findings VALUES (?,?,1,1,'warning','bug','Issue',NULL,'accepted')", (finding, review))
            db.execute("INSERT INTO discussion_turns VALUES (?,?,?,'Original question','Original answer','succeeded',1,?,?,?,NULL)", (turn,finding,str(uuid4()),NOW,NOW,NOW))
            previous = dict(db.execute('SELECT * FROM discussion_turns WHERE id=?',(turn,)).fetchone())
    with closing(open_database(path)) as db:
        migrated = dict(db.execute('SELECT * FROM discussion_turns WHERE id=?',(turn,)).fetchone())
        assert migrated.pop('conversation_id') == finding
        assert migrated == previous
        assert db.execute('SELECT resolution FROM findings WHERE id=?',(finding,)).fetchone()[0] == 'accepted'
        assert db.execute('SELECT finding_id FROM discussion_conversations WHERE id=?',(finding,)).fetchone()[0] == finding
        with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
            db.execute('UPDATE discussion_turns SET conversation_id=? WHERE id=?',(str(uuid4()),turn))
