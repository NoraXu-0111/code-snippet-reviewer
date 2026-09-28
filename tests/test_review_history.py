from contextlib import closing
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.database import open_database
from test_reviews import FakeReviewer, create, finish, start


def test_history_is_scoped_ordered_and_keeps_previous_resolutions(tmp_path):
    settings=Settings(database_path=tmp_path/'history.db')
    with TestClient(create_app(settings,reviewer=FakeReviewer())) as client:
        snippet=create(client); other=create(client)
        assert client.get(f'/api/snippets/{snippet}/reviews').json()=={'reviews':[]}
        first=finish(client,start(client,snippet))
        finding=first['findings'][0]
        client.patch(f"/api/findings/{finding['id']}",json={'resolution':'accepted'})
        second=finish(client,start(client,snippet))
        finish(client,start(client,other))
        with closing(open_database(settings.database_path)) as db:
            db.execute('UPDATE review_runs SET created_at=? WHERE snippet_id=?',('2026-09-28T00:00:00Z',snippet))
        history=client.get(f'/api/snippets/{snippet}/reviews').json()['reviews']
        assert [run['id'] for run in history]==[second['review']['id'],first['review']['id']]
        assert client.get(f"/api/reviews/{first['review']['id']}").json()['findings'][0]['resolution']=='accepted'
        assert client.get(f'/api/snippets/{uuid4()}/reviews').status_code==404
