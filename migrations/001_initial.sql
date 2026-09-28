CREATE TABLE snippets (
  id TEXT PRIMARY KEY NOT NULL,
  title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 120),
  language TEXT NOT NULL CHECK (length(trim(language)) BETWEEN 1 AND 50),
  code TEXT NOT NULL CHECK (length(code) BETWEEN 1 AND 100000),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE review_runs (
  id TEXT PRIMARY KEY NOT NULL,
  snippet_id TEXT NOT NULL REFERENCES snippets(id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  CHECK (
    (status = 'queued' AND started_at IS NULL AND finished_at IS NULL AND error IS NULL)
    OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL AND error IS NULL)
    OR (status = 'succeeded' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error IS NULL)
    OR (status = 'failed' AND finished_at IS NOT NULL AND error IS NOT NULL AND length(trim(error)) > 0)
  )
) STRICT;

CREATE UNIQUE INDEX one_active_review_per_snippet
  ON review_runs(snippet_id) WHERE status IN ('queued', 'running');
CREATE INDEX review_runs_by_snippet ON review_runs(snippet_id, created_at DESC);
CREATE INDEX snippets_by_language ON snippets(language);

CREATE TABLE findings (
  id TEXT PRIMARY KEY NOT NULL,
  review_run_id TEXT NOT NULL REFERENCES review_runs(id) ON DELETE RESTRICT,
  start_line INTEGER NOT NULL CHECK (start_line >= 1),
  end_line INTEGER NOT NULL CHECK (end_line >= start_line),
  severity TEXT NOT NULL CHECK (severity IN ('critical', 'warning', 'info')),
  category TEXT NOT NULL CHECK (category IN ('bug', 'style', 'performance', 'security')),
  description TEXT NOT NULL CHECK (length(trim(description)) > 0),
  suggested_fix TEXT,
  resolution TEXT NOT NULL DEFAULT 'open' CHECK (resolution IN ('open', 'accepted', 'dismissed'))
) STRICT;

CREATE INDEX findings_by_review ON findings(review_run_id);
