import asyncio
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from .contracts import CreateDiscussionTurn, DiscussionConversation, DiscussionDetail, DiscussionTurn, Finding, ReviewStatus, Snippet
from .database import open_database
from .discussion_provider import DiscussionFailure, DiscussionProvider
from .reviews import now
from .tracing import trace_subject


class DiscussionConflict(Exception):
    pass


class DiscussionNotConfigured(Exception):
    pass


def ensure_default_conversation(db: sqlite3.Connection, finding_id: UUID | str) -> None:
    if db.execute("SELECT 1 FROM findings WHERE id = ?", (str(finding_id),)).fetchone() is None:
        raise LookupError("Finding not found")
    # Original conversation uses the finding ID. This keeps old clients/drafts stable.
    db.execute("INSERT OR IGNORE INTO discussion_conversations (id, finding_id, created_at) VALUES (?, ?, ?)",
               (str(finding_id), str(finding_id), now()))


def get_discussion(db: sqlite3.Connection, finding_id: UUID | str, conversation_id: UUID | str | None = None) -> DiscussionDetail:
    ensure_default_conversation(db, finding_id)
    selected = str(conversation_id or finding_id)
    if db.execute("SELECT 1 FROM discussion_conversations WHERE id=? AND finding_id=?", (selected, str(finding_id))).fetchone() is None:
        raise LookupError("Conversation not found for this finding")
    conversations = db.execute("SELECT * FROM discussion_conversations WHERE finding_id=? ORDER BY created_at, rowid", (str(finding_id),)).fetchall()
    rows = db.execute("SELECT * FROM discussion_turns WHERE conversation_id = ? ORDER BY created_at, rowid", (selected,))
    active = db.execute("SELECT 1 FROM discussion_turns WHERE finding_id=? AND status IN ('queued','running')", (str(finding_id),)).fetchone()
    return DiscussionDetail(conversation_id=selected, conversations=[DiscussionConversation.model_validate(dict(row)) for row in conversations],
                            has_active_reply=active is not None, turns=[DiscussionTurn.model_validate(dict(row)) for row in rows])


def create_conversation(db: sqlite3.Connection, finding_id: UUID, request_id: UUID) -> tuple[DiscussionConversation, bool]:
    db.execute("BEGIN IMMEDIATE")
    try:
        ensure_default_conversation(db, finding_id)
        existing = db.execute("SELECT * FROM discussion_conversations WHERE id=?", (str(request_id),)).fetchone()
        if existing:
            if existing['finding_id'] != str(finding_id):
                raise DiscussionConflict("This conversation request ID belongs to another finding.")
            db.commit()
            return DiscussionConversation.model_validate(dict(existing)), False
        if db.execute("SELECT 1 FROM findings WHERE id=?", (str(request_id),)).fetchone():
            raise DiscussionConflict("This request ID is reserved for an original finding conversation.")
        if db.execute("SELECT 1 FROM discussion_turns WHERE finding_id=? AND status IN ('queued','running')", (str(finding_id),)).fetchone():
            raise DiscussionConflict("Wait for the current reply to finish before starting a new conversation.")
        conversation = DiscussionConversation(id=request_id, finding_id=finding_id, created_at=now())
        db.execute("INSERT INTO discussion_conversations VALUES (?,?,?)", (str(request_id),str(finding_id),conversation.created_at.isoformat()))
        db.commit()
        return conversation, True
    except Exception:
        db.rollback()
        raise


def load_context(db: sqlite3.Connection, turn: DiscussionTurn) -> tuple[Snippet, Finding, list[DiscussionTurn]]:
    finding = Finding.model_validate(dict(db.execute("SELECT * FROM findings WHERE id = ?", (str(turn.finding_id),)).fetchone()))
    snippet = Snippet.model_validate(dict(db.execute(
        "SELECT s.* FROM snippets s JOIN review_runs r ON r.snippet_id = s.id WHERE r.id = ?",
        (str(finding.review_run_id),),
    ).fetchone()))
    rows = db.execute("""SELECT * FROM discussion_turns
        WHERE conversation_id = ? AND status = 'succeeded'
        AND (created_at, rowid) < (SELECT created_at, rowid FROM discussion_turns WHERE id = ?)
        ORDER BY created_at DESC, rowid DESC LIMIT 10""", (str(turn.conversation_id), str(turn.id))).fetchall()
    return snippet, finding, [DiscussionTurn.model_validate(dict(row)) for row in reversed(rows)]


class DiscussionService:
    """One process per database, with attempt-guarded writes and durable questions."""

    def __init__(self, path: Path, provider: DiscussionProvider, timeout: float, slots: asyncio.Semaphore, *, configured: bool = True):
        self.path, self.provider, self.timeout, self.slots = path, provider, timeout, slots
        self.configured = configured
        self.tasks: set[asyncio.Task] = set()

    def recover_interrupted(self) -> None:
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute("""UPDATE discussion_turns SET status = 'failed', finished_at = ?, error = ?
                WHERE status IN ('queued', 'running')""", (now(), "Reply interrupted by a server restart. Please retry."))

    def submit(self, finding_id: UUID, payload: CreateDiscussionTurn) -> tuple[DiscussionTurn, bool]:
        with closing(open_database(self.path, migrate=False)) as db:
            # Serialize replay lookup, active check, and insert, even across connections.
            db.execute("BEGIN IMMEDIATE")
            try:
                ensure_default_conversation(db, finding_id)
                conversation_id = payload.conversation_id or finding_id
                if db.execute("SELECT 1 FROM discussion_conversations WHERE id=? AND finding_id=?", (str(conversation_id),str(finding_id))).fetchone() is None:
                    raise LookupError("Conversation not found for this finding")
                existing = db.execute("SELECT * FROM discussion_turns WHERE finding_id = ? AND client_request_id = ?",
                                      (str(finding_id), str(payload.client_request_id))).fetchone()
                if existing:
                    if existing["user_message"] != payload.message or existing["conversation_id"] != str(conversation_id):
                        raise DiscussionConflict("This request ID was already used for a different question or conversation.")
                    db.commit()
                    return DiscussionTurn.model_validate(dict(existing)), False
                if db.execute("SELECT 1 FROM discussion_turns WHERE finding_id = ? AND status IN ('queued', 'running')", (str(finding_id),)).fetchone():
                    raise DiscussionConflict("This finding already has a reply in progress. Refresh the conversation.")
                if not self.configured:
                    raise DiscussionNotConfigured()
                turn = DiscussionTurn(id=uuid4(), finding_id=finding_id, conversation_id=conversation_id, client_request_id=payload.client_request_id,
                                      user_message=payload.message, status=ReviewStatus.QUEUED, attempt=1, created_at=now())
                db.execute("""INSERT INTO discussion_turns
                    (id, finding_id, conversation_id, client_request_id, user_message, status, attempt, created_at)
                    VALUES (?, ?, ?, ?, ?, 'queued', 1, ?)""",
                    (str(turn.id), str(finding_id), str(conversation_id), str(payload.client_request_id), turn.user_message, turn.created_at.isoformat()))
                db.commit()
            except Exception:
                db.rollback()
                raise
        self._schedule(turn)
        return turn, True

    def retry(self, turn_id: UUID, attempt: int) -> DiscussionTurn:
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT * FROM discussion_turns WHERE id = ?", (str(turn_id),)).fetchone()
                if row is None:
                    raise LookupError("Discussion turn not found")
                latest = db.execute("SELECT id FROM discussion_turns WHERE conversation_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (row["conversation_id"],)).fetchone()
                if row["status"] != "failed" or row["attempt"] != attempt or latest["id"] != str(turn_id):
                    raise DiscussionConflict("Only the latest failed reply can be retried at its current attempt. Refresh the conversation.")
                if db.execute("SELECT 1 FROM discussion_turns WHERE finding_id=? AND status IN ('queued','running')", (row['finding_id'],)).fetchone():
                    raise DiscussionConflict("This finding already has a reply in progress. Wait for it to finish.")
                if not self.configured:
                    raise DiscussionNotConfigured()
                updated = db.execute("""UPDATE discussion_turns SET status = 'queued', attempt = attempt + 1,
                    started_at = NULL, finished_at = NULL, error = NULL, assistant_message = NULL
                    WHERE id = ? RETURNING *""", (str(turn_id),)).fetchone()
                turn = DiscussionTurn.model_validate(dict(updated))
                db.commit()
            except Exception:
                db.rollback()
                raise
        self._schedule(turn)
        return turn

    def _schedule(self, turn: DiscussionTurn) -> None:
        task = asyncio.create_task(self._execute(turn))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _fail(self, turn: DiscussionTurn, message: str) -> None:
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute("""UPDATE discussion_turns SET status = 'failed', finished_at = ?, error = ?
                WHERE id = ? AND attempt = ? AND status IN ('queued', 'running')""",
                (now(), message, str(turn.id), turn.attempt))

    def _succeed(self, turn: DiscussionTurn, answer: str) -> None:
        if not isinstance(answer, str) or not answer.strip():
            raise DiscussionFailure("The AI returned an empty reply. Please retry.")
        with closing(open_database(self.path, migrate=False)) as db:
            db.execute("""UPDATE discussion_turns SET status = 'succeeded', assistant_message = ?, finished_at = ?
                WHERE id = ? AND attempt = ? AND status = 'running'""", (answer, now(), str(turn.id), turn.attempt))

    async def _execute(self, turn: DiscussionTurn) -> None:
        try:
            async with asyncio.timeout(self.timeout):
                async with self.slots:
                    with closing(open_database(self.path, migrate=False)) as db:
                        changed = db.execute("""UPDATE discussion_turns SET status = 'running', started_at = ?
                            WHERE id = ? AND attempt = ? AND status = 'queued'""", (now(), str(turn.id), turn.attempt)).rowcount
                        if not changed:
                            return
                        snippet, finding, history = load_context(db, turn)
                    with trace_subject(turn.id, turn.attempt):
                        answer = await self.provider.reply(snippet, finding, history, turn.user_message)
                    self._succeed(turn, answer)
        except asyncio.CancelledError:
            self._fail(turn, "Reply interrupted by server shutdown. Please retry.")
            raise
        except TimeoutError:
            self._fail(turn, "Reply timed out. Please retry, or ask a shorter question.")
        except DiscussionFailure as exc:
            self._fail(turn, str(exc))
        except Exception as exc:
            logging.getLogger(__name__).error("Discussion turn %s failed (%s)", turn.id, type(exc).__name__)
            self._fail(turn, "Could not complete this reply. Please retry.")

    async def close(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.recover_interrupted()
