import asyncio
import sqlite3
import time
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.contracts import DiscussionTurn
from backend.database import open_database
from backend.discussion_provider import DiscussionFailure
from backend.discussions import DiscussionService
from test_reviews import FakeReviewer, create, finish, start


class FakeDiscussion:
    def __init__(self, *, answer="Check for an empty list first.", error=None, delay=0):
        self.answer, self.error, self.delay = answer, error, delay
        self.calls = []

    async def reply(self, snippet, finding, history, question):
        self.calls.append((snippet, finding, history, question))
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer


def setup(client):
    snippet = create(client)
    review = finish(client, start(client, snippet))
    return snippet, review["review"]["id"], review["findings"][0]["id"]


def ask(client, finding, message="Why?", key=None):
    return client.post(f"/api/findings/{finding}/discussion", json={"message": message, "clientRequestId": key or str(uuid4())})


def history(client, finding):
    response = client.get(f"/api/findings/{finding}/discussion")
    assert response.status_code == 200
    return response.json()["turns"]


def settled(client, finding):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        turns = history(client, finding)
        if turns and turns[-1]["status"] in ("succeeded", "failed"):
            return turns
        time.sleep(.01)
    pytest.fail("Discussion did not finish")


def test_followups_persistence_resolution_and_rerun_isolation(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeDiscussion(delay=.04)
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        snippet, review, finding = setup(client)
        assert history(client, finding) == []
        assert ask(client, finding, "Show an example").status_code == 202
        # Resolution is independent even while generating.
        assert client.patch(f"/api/findings/{finding}", json={"resolution": "accepted"}).status_code == 200
        first = settled(client, finding)[0]
        assert first["status"] == "succeeded"
        assert ask(client, finding, "Explain that example").status_code == 202
        saved = settled(client, finding)
        assert len(saved) == 2
        assert [t.user_message for t in fake.calls[1][2]] == ["Show an example"]
        assert fake.calls[1][2][0].assistant_message == first["assistantMessage"]
        new_run = finish(client, start(client, snippet))
        new_finding = new_run["findings"][0]["id"]
        assert history(client, new_finding) == []
        assert history(client, finding) == saved
        ask(client, new_finding, "Different finding")
        settled(client, new_finding)
        assert fake.calls[-1][2] == []
        assert client.get(f"/api/reviews/{review}").json()["findings"][0]["resolution"] == "accepted"
        assert client.get(f"/api/snippets/{snippet}").json()["snippet"]["code"] == "result = 1 / 0"
    with TestClient(create_app(settings, discussion_provider=fake)) as client:
        assert history(client, finding) == saved
        for resolution in ("dismissed", "open"):
            client.patch(f"/api/findings/{finding}", json={"resolution": resolution})
            assert history(client, finding) == saved


def test_idempotent_replay_active_conflict_and_key_conflict(tmp_path):
    fake = FakeDiscussion(delay=.15)
    settings = Settings(database_path=tmp_path / "test.db")
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        _, _, finding = setup(client)
        key = str(uuid4())
        first = ask(client, finding, key=key)
        replay = ask(client, finding, key=key)
        assert first.status_code == 202 and replay.status_code == 200
        assert first.json()["id"] == replay.json()["id"]
        assert ask(client, finding).status_code == 409
        conflict = ask(client, finding, "Different text", key)
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "discussion_conflict"
        assert client.get("/api/health").status_code == 200
        saved = settled(client, finding)
        assert ask(client, finding, key=key).json() == saved[0]
        assert len(fake.calls) == 1 and len(saved) == 1
    # Recovery of an existing submission works even if the key was removed.
    with TestClient(create_app(Settings(database_path=settings.database_path, openai_api_key=None))) as client:
        assert ask(client, finding, key=key).status_code == 200
        assert ask(client, finding).status_code == 503
        assert len(history(client, finding)) == 1


@pytest.mark.parametrize("fake,expected", [
    (FakeDiscussion(error=DiscussionFailure("Provider quota reached")), "quota"),
    (FakeDiscussion(error=RuntimeError("SECRET_PROVIDER_PAYLOAD")), "Could not complete"),
    (FakeDiscussion(answer=" \n\t"), "empty"),
    (FakeDiscussion(delay=1), "timed out"),
])
def test_failures_retry_in_place_and_stale_attempt(tmp_path, fake, expected):
    settings = Settings(database_path=tmp_path / "test.db", review_timeout_seconds=.1)
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        _, _, finding = setup(client)
        ask(client, finding)
        failed = settled(client, finding)[0]
        assert failed["status"] == "failed" and failed["assistantMessage"] is None
        assert expected in failed["error"] and "SECRET" not in failed["error"]
        fake.error, fake.delay, fake.answer = None, .03, "A valid answer"
        retry = client.post(f"/api/discussion-turns/{failed['id']}/retry", json={"attempt": 1})
        assert retry.status_code == 202 and retry.json()["attempt"] == 2
        assert retry.json()["createdAt"] == failed["createdAt"]
        assert client.post(f"/api/discussion-turns/{failed['id']}/retry", json={"attempt": 1}).status_code == 409
        turns = settled(client, finding)
        assert len(turns) == 1 and turns[0]["id"] == failed["id"]
        assert turns[0]["status"] == "succeeded" and turns[0]["error"] is None
        assert len(fake.calls) == 2 and fake.calls[-1][2] == []


def test_only_latest_failed_turn_can_retry_and_failures_not_in_context(tmp_path):
    fake = FakeDiscussion(error=DiscussionFailure("Failed"))
    with TestClient(create_app(Settings(database_path=tmp_path / "test.db"), reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        _, _, finding = setup(client)
        ask(client, finding, "First failure")
        failed = settled(client, finding)[0]
        fake.error = None
        ask(client, finding, "New question")
        assert settled(client, finding)[-1]["status"] == "succeeded"
        assert fake.calls[-1][2] == []
        assert client.post(f"/api/discussion-turns/{failed['id']}/retry", json={"attempt": 1}).status_code == 409


def test_shutdown_and_startup_recovery_preserve_questions(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeDiscussion(delay=30)
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        _, _, finding = setup(client)
        turn = ask(client, finding).json()
        assert history(client, finding)[0]["status"] in ("queued", "running")
    with closing(open_database(settings.database_path)) as db:
        assert db.execute("SELECT status FROM discussion_turns WHERE id = ?", (turn["id"],)).fetchone()[0] == "failed"
        # Simulate a crash that left a queued turn, distinct from graceful shutdown.
        db.execute("UPDATE discussion_turns SET status='queued', started_at=NULL, finished_at=NULL, error=NULL WHERE id=?", (turn["id"],))
    with TestClient(create_app(settings, discussion_provider=FakeDiscussion())) as client:
        recovered = history(client, finding)[0]
        assert recovered["userMessage"] == "Why?" and "restart" in recovered["error"]
        assert client.post(f"/api/discussion-turns/{turn['id']}/retry", json={"attempt": 1}).status_code == 202
        assert settled(client, finding)[0]["status"] == "succeeded"


def test_context_recent_ten_ordering_and_foreign_finding_exclusion(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeDiscussion()
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=fake)) as client:
        _, _, finding = setup(client)
        _, _, other = setup(client)
        # Same timestamp exercises the rowid tie-breaker, plus a failed exchange.
        with closing(open_database(settings.database_path)) as db:
            for i in range(12):
                db.execute("""INSERT INTO discussion_turns VALUES (?, ?, ?, ?, ?, 'succeeded', 1, ?, ?, ?, NULL)""",
                           (str(uuid4()), finding, str(uuid4()), f"q{i}", f"a{i}", *(["2020-01-01T00:00:00Z"] * 3)))
            db.execute("INSERT INTO discussion_turns VALUES (?, ?, ?, 'FAILED', NULL, 'failed', 1, ?, NULL, ?, 'Failure')",
                       (str(uuid4()), finding, str(uuid4()), *(["2020-01-01T00:00:00Z"] * 2)))
        ask(client, other, "PRIVATE_OTHER_FINDING")
        settled(client, other)
        ask(client, finding, "Continue")
        assert len(settled(client, finding)) == 14
        snippet, selected, turns, question = fake.calls[-1]
        assert str(selected.id) == finding and question == "Continue"
        assert [t.user_message for t in turns] == [f"q{i}" for i in range(2, 12)]


def test_unknown_invalid_and_missing_configuration(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db", openai_api_key=None)
    with TestClient(create_app(settings, reviewer=FakeReviewer())) as client:
        _, _, finding = setup(client)
        assert ask(client, finding).status_code == 503
        assert history(client, finding) == []
        assert client.get(f"/api/findings/{uuid4()}/discussion").status_code == 404
        assert ask(client, str(uuid4())).status_code == 404
        assert client.post(f"/api/discussion-turns/{uuid4()}/retry", json={"attempt": 1}).status_code == 404
        for message in ("", " \n\t", "x" * 4001):
            assert ask(client, finding, message).status_code == 400
        assert ask(client, finding, key="not-a-uuid").status_code == 400
        assert client.post(f"/api/discussion-turns/{uuid4()}/retry", json={"attempt": True}).status_code == 400


def test_database_constraints_and_stale_completion_cannot_overwrite_retry(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    with TestClient(create_app(settings, reviewer=FakeReviewer(), discussion_provider=FakeDiscussion(error=DiscussionFailure("failed")))) as client:
        _, _, finding = setup(client)
        ask(client, finding)
        failed = DiscussionTurn.model_validate(settled(client, finding)[0])
    with closing(open_database(settings.database_path)) as db:
        db.execute("UPDATE discussion_turns SET status='running', attempt=2, started_at=created_at, finished_at=NULL, error=NULL WHERE id=?", (str(failed.id),))
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute("UPDATE discussion_turns SET status='succeeded', finished_at=created_at WHERE id=?", (str(failed.id),))
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            db.execute("""INSERT INTO discussion_turns (id, finding_id, client_request_id, user_message, status, attempt, created_at)
                VALUES (?, ?, ?, 'Another', 'queued', 1, ?)""", (str(uuid4()), finding, str(uuid4()), failed.created_at.isoformat()))
    service = DiscussionService(settings.database_path, FakeDiscussion(), 60, asyncio.Semaphore(2))
    service._succeed(failed, "STALE ANSWER")
    service._fail(failed, "STALE FAILURE")
    with closing(open_database(settings.database_path)) as db:
        current = DiscussionTurn.model_validate(dict(db.execute("SELECT * FROM discussion_turns WHERE id=?", (str(failed.id),)).fetchone()))
        assert current.attempt == 2 and current.status == "running" and current.assistant_message is None
    service._succeed(current, "CURRENT ANSWER")
    with closing(open_database(settings.database_path)) as db:
        assert db.execute("SELECT assistant_message FROM discussion_turns WHERE id=?", (str(failed.id),)).fetchone()[0] == "CURRENT ANSWER"


def test_shared_concurrency_and_timeout_including_queue(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    reviewer, provider = FakeReviewer(), FakeDiscussion()
    app = create_app(settings, reviewer=reviewer, discussion_provider=provider)
    with TestClient(app) as client:
        snippet, _, finding = setup(client)
        other = create(client)
        assert app.state.reviews.slots is app.state.discussions.slots
        reviewer.delay = .25
        first, second = start(client, snippet), start(client, other)
        app.state.discussions.timeout = .04
        ask(client, finding)
        failed = settled(client, finding)[0]
        assert failed["status"] == "failed" and "timed out" in failed["error"]
        assert failed["startedAt"] is None and provider.calls == []
        assert finish(client, first)["review"]["status"] == "succeeded"
        assert finish(client, second)["review"]["status"] == "succeeded"
