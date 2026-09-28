CREATE TABLE quality_sessions (
    id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    created_at TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    UNIQUE(source_id, reviewer)
) STRICT;
CREATE TABLE quality_annotations (
    session_id TEXT NOT NULL REFERENCES quality_sessions(id),
    case_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision > 0),
    saved_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(session_id, case_id, revision)
) STRICT;
