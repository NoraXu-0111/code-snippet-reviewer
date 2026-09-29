CREATE TABLE discussion_conversations (
  id TEXT PRIMARY KEY NOT NULL,
  finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  UNIQUE (id, finding_id)
) STRICT;
CREATE INDEX conversations_by_finding ON discussion_conversations(finding_id, created_at);
INSERT INTO discussion_conversations (id, finding_id, created_at)
  SELECT f.id, f.id, COALESCE((SELECT MIN(created_at) FROM discussion_turns WHERE finding_id=f.id), r.created_at)
  FROM findings f JOIN review_runs r ON r.id=f.review_run_id;
CREATE TABLE discussion_turns_next (
  id TEXT PRIMARY KEY NOT NULL,
  finding_id TEXT NOT NULL REFERENCES findings(id) ON DELETE RESTRICT,
  conversation_id TEXT NOT NULL,
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
  FOREIGN KEY (conversation_id, finding_id) REFERENCES discussion_conversations(id, finding_id),
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

INSERT INTO discussion_turns_next
  (id, finding_id, conversation_id, client_request_id, user_message, assistant_message, status, attempt, created_at, started_at, finished_at, error)
  SELECT id, finding_id, finding_id, client_request_id, user_message, assistant_message, status, attempt, created_at, started_at, finished_at, error FROM discussion_turns;
DROP TABLE discussion_turns;
ALTER TABLE discussion_turns_next RENAME TO discussion_turns;
CREATE UNIQUE INDEX one_active_turn_per_finding
  ON discussion_turns(finding_id) WHERE status IN ('queued', 'running');
CREATE INDEX discussion_turns_by_conversation ON discussion_turns(conversation_id, created_at);
