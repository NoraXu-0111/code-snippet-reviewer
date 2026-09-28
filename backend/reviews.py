import asyncio
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from .contracts import Finding, ReviewDetail, ReviewRun, ReviewStatus, parse_review_output
from .database import open_database
from .reviewer import Reviewer, ReviewFailure
from .snippets import get_snippet
from .tracing import trace_subject


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActiveReviewError(Exception):
    pass


def get_review(db: sqlite3.Connection, review_id: UUID | str) -> ReviewDetail | None:
    run = db.execute("SELECT * FROM review_runs WHERE id = ?", (str(review_id),)).fetchone()
    if run is None:
        return None
    findings = db.execute("SELECT * FROM findings WHERE review_run_id = ? ORDER BY rowid", (str(review_id),)).fetchall()
    return ReviewDetail(
        review=ReviewRun.model_validate(dict(run)),
        findings=[Finding.model_validate(dict(row)) for row in findings],
    )


class ReviewService:
    """Single-process local runner. SQLite records survive; tasks do not."""

    def __init__(self, path: Path, reviewer: Reviewer, timeout: float, slots: asyncio.Semaphore | None = None):
        self.path = path
        self.reviewer = reviewer
        self.timeout = timeout
        self.tasks: set[asyncio.Task] = set()
        self.slots = slots if slots is not None else asyncio.Semaphore(2)

    def recover_interrupted(self) -> None:
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute(
                "UPDATE review_runs SET status = 'failed', finished_at = ?, error = ? WHERE status IN ('queued', 'running')",
                (now(), "Review interrupted by a server restart. Please retry."),
            )

    def submit(self, snippet_id: UUID) -> ReviewRun:
        with closing(open_database(self.path, migrate=False)) as db:
            detail = get_snippet(db, snippet_id)
            if detail is None:
                raise LookupError("Snippet not found")
            run = ReviewRun(id=uuid4(), snippet_id=snippet_id, status=ReviewStatus.QUEUED, created_at=now())
            try:
                db.execute("INSERT INTO review_runs VALUES (?, ?, ?, ?, ?, ?, ?)", (
                    str(run.id), str(snippet_id), run.status.value, run.created_at.isoformat(), None, None, None,
                ))
            except sqlite3.IntegrityError as exc:
                if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
                    raise ActiveReviewError("This snippet already has a review in progress.") from None
                raise
        task = asyncio.create_task(self._execute(run, detail.snippet))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return run

    def _fail(self, review_id: UUID, message: str) -> None:
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute(
                "UPDATE review_runs SET status = 'failed', finished_at = ?, error = ? WHERE id = ? AND status IN ('queued', 'running')",
                (now(), message, str(review_id)),
            )

    async def _execute(self, run, snippet) -> None:
        try:
            # Bound total time, including waiting for a concurrency slot.
            async with asyncio.timeout(self.timeout):
                async with self.slots:
                    with closing(open_database(self.path, migrate=False)) as db:
                        changed = db.execute(
                            "UPDATE review_runs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
                            (now(), str(run.id)),
                        ).rowcount
                    if not changed:
                        return
                    with trace_subject(run.id):
                        output = await self.reviewer.review(snippet)
                    output = parse_review_output(output.model_dump(), snippet.code)
                    with closing(open_database(self.path, migrate=False)) as db:
                        db.execute("BEGIN IMMEDIATE")
                        try:
                            current = db.execute("SELECT status FROM review_runs WHERE id = ?", (str(run.id),)).fetchone()
                            if current["status"] != "running":
                                db.rollback()
                                return
                            for finding in output.findings:
                                db.execute("INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                                    str(uuid4()), str(run.id), finding.start_line, finding.end_line,
                                    finding.severity.value, finding.category.value, finding.description,
                                    finding.suggested_fix, "open",
                                ))
                            db.execute("UPDATE review_runs SET status = 'succeeded', finished_at = ? WHERE id = ?", (now(), str(run.id)))
                            db.commit()
                        except Exception:
                            db.rollback()
                            raise
        except asyncio.CancelledError:
            self._fail(run.id, "Review interrupted by server shutdown. Please retry.")
            raise
        except TimeoutError:
            self._fail(run.id, "Review timed out. Please retry, or use a shorter snippet.")
        except ReviewFailure as exc:
            self._fail(run.id, str(exc))
        except (ValueError, TypeError):
            self._fail(run.id, "The review returned invalid findings. Please retry.")
        except Exception as exc:
            # Provider exceptions can contain source code or credentials. Record
            # only the exception class, not its body or traceback.
            logging.getLogger(__name__).error("Review %s failed (%s)", run.id, type(exc).__name__)
            self._fail(run.id, "Could not complete this review. Please retry.")

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Also catches tasks canceled before their coroutine ever started.
        self.recover_interrupted()
