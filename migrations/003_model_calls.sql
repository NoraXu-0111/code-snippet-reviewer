CREATE TABLE model_calls (
  id TEXT PRIMARY KEY NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('review', 'discussion')),
  subject_id TEXT NOT NULL,
  attempt INTEGER NOT NULL CHECK (attempt >= 1),
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled', 'interrupted')),
  input_tokens INTEGER,
  output_tokens INTEGER,
  request_id TEXT,
  response_id TEXT,
  error_type TEXT
) STRICT;
CREATE INDEX model_calls_by_subject ON model_calls(subject_id, started_at);
