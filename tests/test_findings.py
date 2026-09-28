from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.database import open_database


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db")
    with TestClient(create_app(settings)) as client:
        snippet = client.post("/api/snippets", json={
            "title": "Two findings", "language": "python", "code": "a = 1\nb = 2\n",
        }).json()
        run_ids = [str(uuid4()), str(uuid4())]
        finding_ids = [str(uuid4()), str(uuid4()), str(uuid4())]
        now = "2026-09-28T00:00:00Z"
        with closing(open_database(settings.database_path)) as db:
            for run_id in run_ids:
                db.execute("INSERT INTO review_runs VALUES (?, ?, 'succeeded', ?, ?, ?, NULL)", (run_id, snippet["id"], now, now, now))
            for index, finding_id in enumerate(finding_ids):
                db.execute("INSERT INTO findings VALUES (?, ?, 1, 2, 'info', 'style', ?, NULL, 'open')",
                           (finding_id, run_ids[0 if index < 2 else 1], f"Finding {index}"))
        yield client, settings, snippet, run_ids, finding_ids


def test_resolution_persists_without_changing_code_or_other_findings(workspace):
    client, settings, snippet, runs, ids = workspace
    first_before = client.get(f"/api/reviews/{runs[0]}").json()
    for resolution in ["accepted", "accepted", "dismissed", "open", "accepted"]:
        response = client.patch(f"/api/findings/{ids[0]}", json={"resolution": resolution})
        assert response.status_code == 200
        assert response.json()["resolution"] == resolution
        assert response.json()["id"] == ids[0]
    assert client.get(f"/api/snippets/{snippet['id']}").json()["snippet"]["code"] == snippet["code"]
    first_after = client.get(f"/api/reviews/{runs[0]}").json()
    assert first_after["review"] == first_before["review"]
    assert first_after["findings"][1]["resolution"] == "open"
    assert client.get(f"/api/reviews/{runs[1]}").json()["findings"][0]["resolution"] == "open"
    with TestClient(create_app(settings)) as restarted:
        result = restarted.get(f"/api/reviews/{runs[0]}").json()
        assert result["findings"][0]["resolution"] == "accepted"


@pytest.mark.parametrize("payload", [
    {"resolution": "fixed"}, {"resolution": None}, {},
    {"resolution": "accepted", "description": "changed"},
])
def test_invalid_mutation_does_not_change_finding(workspace, payload):
    client, _, _, runs, ids = workspace
    before = client.get(f"/api/reviews/{runs[0]}").json()
    response = client.patch(f"/api/findings/{ids[0]}", json=payload)
    assert response.status_code == 400
    assert client.get(f"/api/reviews/{runs[0]}").json() == before


def test_missing_finding_returns_not_found(workspace):
    client, *_ = workspace
    response = client.patch(f"/api/findings/{uuid4()}", json={"resolution": "accepted"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
