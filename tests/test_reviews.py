import asyncio
import time
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.contracts import ReviewOutput
from backend.database import open_database
from backend.reviewer import ReviewFailure


FINDING = {"startLine": 1, "endLine": 1, "severity": "warning", "category": "bug", "description": "Division by zero", "suggestedFix": "Check the divisor."}


class FakeReviewer:
    def __init__(self, output=None, delay=0, error=None):
        self.output = output if output is not None else {"findings": [FINDING]}
        self.delay, self.error, self.calls = delay, error, 0

    async def review(self, snippet):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return ReviewOutput.model_validate(self.output)


def create(client):
    response = client.post("/api/snippets", json={"title": "Division", "language": "python", "code": "result = 1 / 0"})
    assert response.status_code == 201
    return response.json()["id"]


def start(client, snippet_id):
    response = client.post(f"/api/snippets/{snippet_id}/reviews", json={"clientRequestId": str(uuid4())})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    return response.json()["id"]


def finish(client, run_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"/api/reviews/{run_id}")
        assert result.status_code == 200
        if result.json()["review"]["status"] in ("succeeded", "failed"):
            return result.json()
        time.sleep(.01)
    pytest.fail("Review did not finish")


def test_review_persistence_and_rerun_isolation(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeReviewer()
    with TestClient(create_app(settings, reviewer=fake)) as client:
        snippet = create(client)
        first_id = start(client, snippet)
        first = finish(client, first_id)
        assert first["review"]["status"] == "succeeded"
        assert first["findings"][0]["startLine"] == 1
        with closing(open_database(settings.database_path)) as db:
            db.execute("UPDATE findings SET resolution = 'accepted' WHERE review_run_id = ?", (first_id,))
        second_id = start(client, snippet)
        second = finish(client, second_id)
        assert second_id != first_id
        assert second["findings"][0]["resolution"] == "open"
        assert second["findings"][0]["id"] != first["findings"][0]["id"]
        assert client.get(f"/api/snippets/{snippet}").json()["latestReview"]["id"] == second_id
    with TestClient(create_app(settings, reviewer=fake)) as client:
        assert client.get(f"/api/reviews/{first_id}").json()["findings"][0]["resolution"] == "accepted"
        assert client.get(f"/api/reviews/{second_id}").json()["review"]["status"] == "succeeded"


def test_duplicate_trigger_is_rejected_while_polling_remains_responsive(tmp_path):
    fake = FakeReviewer(delay=.15)
    with TestClient(create_app(Settings(database_path=tmp_path / "test.db"), reviewer=fake)) as client:
        snippet = create(client)
        run_id = start(client, snippet)
        duplicate = client.post(f"/api/snippets/{snippet}/reviews", json={"clientRequestId": str(uuid4())})
        assert duplicate.status_code == 409
        assert client.get("/api/health").status_code == 200
        assert finish(client, run_id)["review"]["status"] == "succeeded"
        assert fake.calls == 1


@pytest.mark.parametrize("fake,expected_status,expected_error", [
    (FakeReviewer(output={"findings": []}), "succeeded", None),
    (FakeReviewer(output={"findings": [{**FINDING, "endLine": 99}]}), "failed", "invalid"),
    (FakeReviewer(error=ReviewFailure("OpenAI quota or rate limit reached.")), "failed", "quota"),
    (FakeReviewer(delay=1), "failed", "timed out"),
])
def test_empty_invalid_provider_failure_and_timeout(tmp_path, fake, expected_status, expected_error):
    settings = Settings(database_path=tmp_path / "test.db", review_timeout_seconds=.1)
    with TestClient(create_app(settings, reviewer=fake)) as client:
        snippet = create(client)
        run_id = start(client, snippet)
        result = finish(client, run_id)
        assert result["review"]["status"] == expected_status
        assert result["findings"] == []
        if expected_error:
            assert expected_error in result["review"]["error"]
        else:
            assert result["review"]["error"] is None
        fake.delay, fake.error, fake.output = 0, None, {"findings": []}
        assert finish(client, start(client, snippet))["review"]["status"] == "succeeded"


def test_result_persistence_is_atomic(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeReviewer(output={"findings": [FINDING, {**FINDING, "description": "Reject"}]})
    with TestClient(create_app(settings, reviewer=fake)) as client:
        snippet = create(client)
        with closing(open_database(settings.database_path)) as db:
            db.execute("""CREATE TRIGGER fail_second_finding BEFORE INSERT ON findings
                WHEN NEW.description = 'Reject' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        result = finish(client, start(client, snippet))
        assert result["review"]["status"] == "failed"
        assert result["findings"] == []


def test_recover_interrupted_and_cancel_on_shutdown(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    fake = FakeReviewer(delay=30)
    with TestClient(create_app(settings, reviewer=fake)) as client:
        snippet = create(client)
        run_id = start(client, snippet)
    with closing(open_database(settings.database_path)) as db:
        assert db.execute("SELECT status FROM review_runs WHERE id = ?", (run_id,)).fetchone()[0] == "failed"
        interrupted = str(uuid4())
        db.execute("INSERT INTO review_runs VALUES (?, ?, 'running', ?, ?, NULL, NULL)", (interrupted, snippet, "2026-09-28T00:00:00Z", "2026-09-28T00:00:00Z"))
    with TestClient(create_app(settings, reviewer=FakeReviewer())) as client:
        recovered = client.get(f"/api/reviews/{interrupted}").json()
        assert recovered["review"]["status"] == "failed"
        assert "restart" in recovered["review"]["error"]
        assert finish(client, start(client, snippet))["review"]["status"] == "succeeded"


def test_missing_key_and_unknown_ids(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db", openai_api_key=None)
    with TestClient(create_app(settings)) as client:
        snippet = create(client)
        assert client.post(f"/api/snippets/{snippet}/reviews", json={"clientRequestId": str(uuid4())}).status_code == 503
        assert client.get(f"/api/snippets/{snippet}").json()["latestReview"] is None
    with TestClient(create_app(settings, reviewer=FakeReviewer())) as client:
        assert client.post(f"/api/snippets/{uuid4()}/reviews", json={"clientRequestId": str(uuid4())}).status_code == 404
        assert client.get(f"/api/reviews/{uuid4()}").status_code == 404


@pytest.mark.parametrize("fails", [False, True])
def test_submission_replay_survives_completion_restart_and_missing_key(tmp_path, fails):
    settings = Settings(database_path=tmp_path / "test.db", openai_api_key=None)
    fake = FakeReviewer(delay=.1, error=ReviewFailure("Simulated failure") if fails else None)
    request_id = str(uuid4())
    with TestClient(create_app(settings, reviewer=fake)) as client:
        snippet = create(client)
        url = f"/api/snippets/{snippet}/reviews"
        first = client.post(url, json={"clientRequestId": request_id})
        assert first.status_code == 202
        run_id = first.json()["id"]
        replay = client.post(url, json={"clientRequestId": request_id})
        assert replay.status_code == 200
        assert replay.json()["id"] == run_id
        result = finish(client, run_id)
        replay = client.post(url, json={"clientRequestId": request_id})
        assert replay.status_code == 200
        assert replay.json() == result["review"]
        assert fake.calls == 1
        assert len(client.get(url).json()["reviews"]) == 1
        # The same UUID on another snippet identifies a different submission.
        other = create(client)
        other_run = client.post(f"/api/snippets/{other}/reviews", json={"clientRequestId": request_id})
        assert other_run.status_code == 202
        assert other_run.json()["id"] != run_id
        finish(client, other_run.json()["id"])
        assert fake.calls == 2
    with TestClient(create_app(settings)) as client:
        replay = client.post(url, json={"clientRequestId": request_id})
        assert replay.status_code == 200
        assert replay.json() == result["review"]
        assert client.post(url, json={"clientRequestId": str(uuid4())}).status_code == 503
        assert len(client.get(url).json()["reviews"]) == 1
    # A deliberately new request after failure/success creates one new execution.
    with TestClient(create_app(settings, reviewer=fake)) as client:
        new_run = start(client, snippet)
        assert new_run != run_id
        finish(client, new_run)
        assert fake.calls == 3


def test_review_requires_valid_submission_identity(tmp_path):
    fake = FakeReviewer()
    with TestClient(create_app(Settings(database_path=tmp_path / "test.db"), reviewer=fake)) as client:
        snippet = create(client)
        url = f"/api/snippets/{snippet}/reviews"
        for payload in ({}, {"clientRequestId": "invalid"}):
            assert client.post(url, json=payload).status_code == 400
        assert client.post(url).status_code == 400
        assert client.get(url).json()["reviews"] == []
        assert fake.calls == 0


@pytest.mark.parametrize("outer_transaction", [False, True])
def test_review_detail_uses_one_snapshot_during_concurrent_completion(tmp_path, outer_transaction):
    import sqlite3
    from backend.reviews import get_review

    path = tmp_path / "test.db"
    snippet, run = str(uuid4()), str(uuid4())
    timestamp = "2026-09-28T00:00:00Z"
    with closing(open_database(path)) as writer:
        writer.execute("INSERT INTO snippets VALUES (?, 'Test', 'python', '1 / 0', ?)", (snippet, timestamp))
        writer.execute("INSERT INTO review_runs VALUES (?, ?, 'running', ?, ?, NULL, NULL)", (run, snippet, timestamp, timestamp))

        class InterleavedConnection(sqlite3.Connection):
            completed = False

            def execute(self, sql, parameters=()):
                if sql.startswith("SELECT * FROM findings") and not self.completed:
                    self.completed = True
                    writer.execute("BEGIN IMMEDIATE")
                    writer.execute("INSERT INTO findings VALUES (?, ?, 1, 1, 'warning', 'bug', 'Division by zero', NULL, 'open')", (str(uuid4()), run))
                    writer.execute("UPDATE review_runs SET status='succeeded', finished_at=? WHERE id=?", (timestamp, run))
                    writer.commit()
                return super().execute(sql, parameters)

        with closing(sqlite3.connect(path, isolation_level=None, factory=InterleavedConnection)) as reader:
            reader.row_factory = sqlite3.Row
            if outer_transaction:
                reader.execute("BEGIN")
            result = get_review(reader, run)
            assert result.review.status == "running"
            assert result.findings == []
            assert reader.in_transaction is outer_transaction
            if outer_transaction:
                reader.rollback()
            completed = get_review(reader, run)
            assert completed.review.status == "succeeded"
            assert len(completed.findings) == 1
            assert not reader.in_transaction
            assert get_review(reader, uuid4()) is None
            assert not reader.in_transaction
            # An exception also releases an owned read transaction.
            reader.execute("DROP TABLE findings")
            with pytest.raises(sqlite3.OperationalError):
                get_review(reader, run)
            assert not reader.in_transaction
