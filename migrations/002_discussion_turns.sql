CREATE TABLE discussion_turns (
  id TEXT PRIMARY KEY NOT NULL,
  finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE RESTRICT,
  client_request_id TEXT NOT NULL,
  user_message TEXT NOT NULL CHECK (length(trim(user_message)) BETWEEN 1 AND 4000),
  assistant_message TEXT,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  attempt INTEGER NOT NULL CHECK (attempt >= 1),
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  UNIQUE (finding_id, client_request_id),
  CHECK (
    (status = 'queued' AND started_at IS NULL AND finished_at IS NULL AND error IS NULL)
    OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL AND error IS NULL)
    OR (status = 'succeeded' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND error IS NULL)
    OR (status = 'failed' AND finished_at IS NOT NULL AND error IS NOT NULL AND length(trim(error)) > 0)
  ),
  CHECK (
    (status = 'succeeded' AND assistant_message IS NOT NULL AND length(trim(assistant_message)) > 0)
    OR (status != 'succeeded' AND assistant_message IS NULL)
  )
) STRICT;

CREATE UNIQUE INDEX one_active_turn_per_finding
  ON discussion_turns(finding_id) WHERE status IN ('queued', 'running');
CREATE INDEX discussion_turns_by_finding ON discussion_turns(finding_id, created_at);
