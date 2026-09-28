from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.database import open_database


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(database_path=tmp_path / "snippets.db")
    with TestClient(create_app(settings)) as client:
        yield client, settings


def create(client, title="Example", language="python", code="print(1)\n"):
    response = client.post("/api/snippets", json={"title": title, "language": language, "code": code})
    assert response.status_code == 201
    return response.json()


def test_create_list_detail_and_restart(workspace):
    client, settings = workspace
    code = '\r\n  print("<script>alert(1)</script>")\r\n'
    saved = create(client, "  Example  ", "Python", code)
    assert saved["title"] == "Example"
    assert saved["language"] == "python"
    assert saved["code"] == code
    assert "createdAt" in saved and "created_at" not in saved
    assert client.get(f"/api/snippets/{saved['id']}").json() == {"snippet": saved, "latestReview": None}
    result = client.get("/api/snippets").json()
    assert result["languages"] == ["python"]
    assert result["snippets"][0]["reviewStatus"] == "not_reviewed"
    assert "code" not in result["snippets"][0]
    # A fresh application and connection read the same file, not process memory.
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"/api/snippets/{saved['id']}").json()["snippet"] == saved


@pytest.mark.parametrize("payload", [
    {"title": " ", "language": "python", "code": "x"},
    {"title": "Test", "language": " ", "code": "x"},
    {"title": "Test", "language": "python", "code": " \n"},
    {"title": "Test", "language": "python", "code": "x" * 100_001},
    {"title": "Test", "language": "python", "code": "x", "unexpected": True},
])
def test_invalid_input_is_not_saved(workspace, payload):
    client, _ = workspace
    response = client.post("/api/snippets", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert client.get("/api/snippets").json()["snippets"] == []


def test_filter_latest_review_and_combination(workspace):
    client, settings = workspace
    untouched = create(client, "Untouched")
    failed = create(client, "Latest failed")
    running = create(client, "Working", "typescript")
    reviewed = create(client, "Complete", "typescript")
    now = "2026-09-28T00:00:00Z"
    with closing(open_database(settings.database_path)) as db:
        def run(snippet, status, error=None):
            db.execute("INSERT INTO review_runs VALUES (?, ?, ?, ?, ?, ?, ?)", (
                str(uuid4()), snippet["id"], status, now, now,
                now if status in ("succeeded", "failed") else None, error,
            ))
        run(failed, "succeeded")
        run(failed, "failed", "Provider error")  # Same timestamp; later row wins.
        run(running, "running")
        run(reviewed, "succeeded")
    def ids(query):
        return {row["id"] for row in client.get(f"/api/snippets?{query}").json()["snippets"]}
    assert ids("reviewStatus=not_reviewed") == {untouched["id"]}
    assert ids("reviewStatus=failed") == {failed["id"]}
    assert ids("reviewStatus=in_progress") == {running["id"]}
    assert ids("reviewStatus=reviewed") == {reviewed["id"]}
    assert ids("language=python&reviewStatus=reviewed") == set()
    assert ids("language=typescript&reviewStatus=reviewed") == {reviewed["id"]}
    detail = client.get(f"/api/snippets/{failed['id']}").json()
    assert detail["latestReview"]["status"] == "failed"
    assert client.get("/api/snippets?language=typescript").json()["languages"] == ["python", "typescript"]


def test_not_found_bad_filters_and_parameterized_query(workspace):
    client, _ = workspace
    create(client)
    assert client.get(f"/api/snippets/{uuid4()}").status_code == 404
    assert client.get("/api/snippets/not-a-uuid").status_code == 400
    assert client.get("/api/snippets?reviewStatus=unknown").status_code == 400
    assert client.get("/api/snippets", params={"language": "' OR 1=1 --"}).json()["snippets"] == []
    assert len(client.get("/api/snippets").json()["snippets"]) == 1
