import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import create_app
from backend.config import Settings
from backend.contracts import CreateSnippet, ReviewRun, ReviewStatus, dashboard_status, parse_review_output
from backend.database import migrate_database, open_database

NOW = "2026-09-28T00:00:00Z"


@pytest.fixture
def db(tmp_path):
    connection = open_database(tmp_path / "test.db")
    yield connection
    connection.close()


def insert_snippet(db):
    snippet_id = str(uuid4())
    db.execute("INSERT INTO snippets VALUES (?, ?, ?, ?, ?)", (snippet_id, "Test", "python", "print(1)", NOW))
    return snippet_id


def insert_run(db, snippet_id):
    run_id = str(uuid4())
    db.execute("INSERT INTO review_runs VALUES (?, ?, ?, ?, ?, ?, ?)", (run_id, snippet_id, "queued", NOW, None, None, None))
    return run_id


def test_persistence_and_idempotent_migration(tmp_path):
    filename = tmp_path / "test.db"
    db = open_database(filename)
    snippet_id = insert_snippet(db)
    run_id = insert_run(db, snippet_id)
    db.execute("UPDATE review_runs SET status = 'succeeded', started_at = ?, finished_at = ? WHERE id = ?", (NOW, NOW, run_id))
    finding_id = str(uuid4())
    db.execute("INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (finding_id, run_id, 1, 1, "info", "style", "Unused output", None, "open"))
    db.execute("UPDATE findings SET resolution = 'accepted' WHERE id = ?", (finding_id,))
    migrate_database(db)
    db.close()
    db = open_database(filename)
    try:
        assert db.execute("SELECT resolution FROM findings WHERE id = ?", (finding_id,)).fetchone()[0] == "accepted"
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        assert db.execute("SELECT code FROM snippets WHERE id = ?", (snippet_id,)).fetchone()[0] == "print(1)"
    finally:
        db.close()


def test_active_review_constraint_across_connections(tmp_path):
    filename = tmp_path / "test.db"
    db, other = open_database(filename), open_database(filename)
    try:
        snippet_id = insert_snippet(db)
        run_id = insert_run(db, snippet_id)
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            insert_run(other, snippet_id)
        db.execute("UPDATE review_runs SET status = 'failed', finished_at = ?, error = 'Interrupted' WHERE id = ?", (NOW, run_id))
        insert_run(other, snippet_id)
    finally:
        other.close()
        db.close()


def test_relationships_and_state_constraints(db):
    snippet_id = insert_snippet(db)
    run_id = insert_run(db, snippet_id)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        insert_run(db, str(uuid4()))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        db.execute("UPDATE review_runs SET status = 'succeeded' WHERE id = ?", (run_id,))
    for start, end, severity, resolution in [(3, 1, "info", "open"), (1, 1, "urgent", "open"), (1, 1, "info", "fixed")]:
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute("INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(uuid4()), run_id, start, end, severity, "bug", "Issue", None, resolution))


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    import backend.database as module
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_broken.sql").write_text("CREATE TABLE temporary_table (id INTEGER);\nINVALID SQL;\n")
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    filename = tmp_path / "test.db"
    with pytest.raises(sqlite3.OperationalError):
        open_database(filename)
    with sqlite3.connect(filename) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name = 'temporary_table'").fetchone() is None
        assert db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0


def test_snippet_validation_preserves_code():
    code = "\n  print(1)\r\n"
    result = CreateSnippet(title=" Test ", language="Python", code=code)
    assert result.code == code
    assert result.title == "Test"
    assert result.language == "python"
    for invalid_code in ["  \n", "x" * 100_001]:
        with pytest.raises(ValidationError):
            CreateSnippet(title="Test", language="python", code=invalid_code)


def test_review_output_validation():
    assert parse_review_output({"findings": []}, "code").findings == []
    finding = {"startLine": 1, "endLine": 2, "severity": "warning", "category": "bug", "description": "Issue"}
    assert parse_review_output({"findings": [finding]}, "a\r\nb").findings[0].suggested_fix is None
    with pytest.raises(ValueError, match="exceeds"):
        parse_review_output({"findings": [finding]}, "one line")
    for changes in [{"startLine": 3}, {"severity": "urgent"}, {"startLine": True}]:
        with pytest.raises(ValidationError):
            parse_review_output({"findings": [{**finding, **changes}]}, "a\nb\nc")
    with pytest.raises(ValidationError):
        parse_review_output({"results": []}, "code")


def test_review_state_and_json_aliases():
    payload = {"id": str(uuid4()), "snippetId": str(uuid4()), "status": "queued", "createdAt": NOW}
    review = ReviewRun.model_validate(payload)
    assert review.model_dump(mode="json", by_alias=True)["snippetId"] == payload["snippetId"]
    with pytest.raises(ValidationError, match="Timestamps"):
        ReviewRun.model_validate({**payload, "status": "succeeded"})
    assert dashboard_status(None) == "not_reviewed"
    assert dashboard_status(ReviewStatus.QUEUED) == "in_progress"
    assert dashboard_status(ReviewStatus.RUNNING) == "in_progress"
    assert dashboard_status(ReviewStatus.SUCCEEDED) == "reviewed"
    assert dashboard_status(ReviewStatus.FAILED) == "failed"


def test_api_startup_and_health(tmp_path):
    filename = tmp_path / "test.db"
    with TestClient(create_app(Settings(database_path=filename))) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "connected"}
        assert filename.is_file()
        assert client.get("/api/missing").status_code == 404
        assert "/api/health" in client.get("/openapi.json").json()["paths"]
