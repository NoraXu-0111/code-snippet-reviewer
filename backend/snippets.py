from datetime import datetime, timezone
from sqlite3 import Connection
from uuid import UUID, uuid4

from .contracts import (
    CreateSnippet, DashboardStatus, ReviewRun, Snippet, SnippetDetail,
    SnippetList, SnippetSummary,
)


def create_snippet(db: Connection, payload: CreateSnippet) -> Snippet:
    snippet = Snippet(id=uuid4(), created_at=datetime.now(timezone.utc), **payload.model_dump())
    db.execute(
        "INSERT INTO snippets (id, title, language, code, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(snippet.id), snippet.title, snippet.language, snippet.code, snippet.created_at.isoformat()),
    )
    return snippet


def list_snippets(db: Connection, language: str | None, status: DashboardStatus | None) -> SnippetList:
    # Select the latest run first, then filter. Filtering runs first could expose
    # an old success when the latest attempt has failed.
    rows = db.execute("""
        WITH summaries AS (
            SELECT s.id, s.title, s.language, s.created_at, s.rowid AS insertion_order,
                CASE
                    WHEN r.id IS NULL THEN 'not_reviewed'
                    WHEN r.status IN ('queued', 'running') THEN 'in_progress'
                    WHEN r.status = 'succeeded' THEN 'reviewed'
                    ELSE 'failed'
                END AS review_status
            FROM snippets s
            LEFT JOIN review_runs r ON r.id = (
                SELECT id FROM review_runs
                WHERE snippet_id = s.id
                ORDER BY created_at DESC, rowid DESC LIMIT 1
            )
        )
        SELECT id, title, language, created_at, review_status FROM summaries
        WHERE (? IS NULL OR language = ?) AND (? IS NULL OR review_status = ?)
        ORDER BY created_at DESC, insertion_order DESC
    """, (language, language, status, status)).fetchall()
    languages = [row[0] for row in db.execute("SELECT DISTINCT language FROM snippets ORDER BY language")]
    return SnippetList(snippets=[SnippetSummary.model_validate(dict(row)) for row in rows], languages=languages)


def get_snippet(db: Connection, snippet_id: UUID) -> SnippetDetail | None:
    row = db.execute("SELECT * FROM snippets WHERE id = ?", (str(snippet_id),)).fetchone()
    if row is None:
        return None
    run = db.execute(
        "SELECT * FROM review_runs WHERE snippet_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (str(snippet_id),),
    ).fetchone()
    return SnippetDetail(
        snippet=Snippet.model_validate(dict(row)),
        latest_review=ReviewRun.model_validate(dict(run)) if run else None,
    )
