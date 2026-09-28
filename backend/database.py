import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECT_ROOT, get_settings


def open_database(filename: Path | str, *, migrate: bool = True) -> sqlite3.Connection:
    if str(filename).strip() in ("", ":memory:"):
        raise ValueError("A persistent SQLite file path is required")
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        if migrate:
            migrate_database(db)
        return db
    except Exception:
        db.close()
        raise


def migrate_database(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        name TEXT PRIMARY KEY NOT NULL,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL
    ) STRICT""")
    db.execute("BEGIN IMMEDIATE")
    try:
        for path in sorted((PROJECT_ROOT / "migrations").glob("[0-9]*_*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            previous = db.execute("SELECT checksum FROM schema_migrations WHERE name = ?", (path.name,)).fetchone()
            if previous:
                if previous["checksum"] != checksum:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            # executescript() commits an existing transaction implicitly. Execute
            # complete statements ourselves so SQL and migration metadata stay atomic.
            statement = ""
            for line in sql.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    db.execute(statement)
                    statement = ""
            if statement.strip():
                raise ValueError(f"Incomplete SQL statement in {path.name}")
            db.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                (path.name, checksum, datetime.now(timezone.utc).isoformat()),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


if __name__ == "__main__":
    filename = get_settings().database_path
    open_database(filename).close()
    print(f"Database migrated: {filename}")
