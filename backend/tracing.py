"""Local model-call metadata. Never persist prompts, responses, or exception text."""
import argparse
import asyncio
import json
import logging
import time
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from .database import open_database

_subject: ContextVar[tuple[str, int] | None] = ContextVar('trace_subject', default=None)
_response: ContextVar[dict | None] = ContextVar('trace_response', default=None)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def trace_subject(subject_id, attempt=1):
    token = _subject.set((str(subject_id), attempt))
    try:
        yield
    finally:
        _subject.reset(token)


def record_response(response):
    """Allowlist SDK metadata; content and error messages never enter the span."""
    usage = getattr(response, 'usage', None)
    _response.set({
        'input_tokens': getattr(usage, 'input_tokens', None),
        'output_tokens': getattr(usage, 'output_tokens', None),
        'request_id': getattr(response, '_request_id', None),
        'response_id': getattr(response, 'id', None),
    })


def write(path, sql, params):
    try:
        with closing(open_database(path, migrate=False)) as db:
            db.execute(sql, params)
    except Exception as exc:
        # Observability failure must not turn a valid review into a failure.
        logging.getLogger(__name__).warning('Trace write failed (%s)', type(exc).__name__)


def recover_traces(path):
    write(path, "UPDATE model_calls SET status='interrupted', finished_at=?, error_type='ProcessInterrupted' WHERE status='running'", (timestamp(),))


def traced(operation):
    def decorate(fn):
        @wraps(fn)
        async def wrapped(self, *args, **kwargs):
            subject = _subject.get()
            if subject is None:
                return await fn(self, *args, **kwargs)
            call_id, started = str(uuid4()), time.monotonic()
            path = self.settings.database_path
            prompt_version = self.prompt_version
            write(path, """INSERT INTO model_calls
                (id, operation, subject_id, attempt, model, prompt_version, started_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running')""",
                (call_id, operation, *subject, self.settings.openai_model, prompt_version, timestamp()))
            token = _response.set(None)
            status, error_type = 'succeeded', None
            try:
                return await fn(self, *args, **kwargs)
            except BaseException as exc:
                status = 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
                error_type = type(exc).__name__
                raise
            finally:
                meta = _response.get() or {}
                write(path, """UPDATE model_calls SET finished_at=?, duration_ms=?, status=?,
                    input_tokens=?, output_tokens=?, request_id=?, response_id=?, error_type=? WHERE id=?""",
                    (timestamp(), round((time.monotonic() - started) * 1000), status,
                     meta.get('input_tokens'), meta.get('output_tokens'), meta.get('request_id'),
                     meta.get('response_id'), error_type, call_id))
                _response.reset(token)
        return wrapped
    return decorate


if __name__ == '__main__':
    from .config import get_settings
    parser = argparse.ArgumentParser(description='Read local call metadata (no code, prompts, or replies).')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--subject', help='Review run ID, discussion turn ID, or eval case attempt ID')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    path = args.database or get_settings().database_path
    with closing(open_database(path)) as db:
        rows = db.execute('SELECT * FROM model_calls WHERE (? IS NULL OR subject_id=?) ORDER BY started_at DESC, rowid DESC LIMIT ?',
                          (args.subject, args.subject, max(1, min(args.limit, 1000)))).fetchall()
    print(json.dumps([dict(row) for row in rows], indent=2))
