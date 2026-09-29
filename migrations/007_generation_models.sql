-- Preserve unknown legacy model identity as NULL; backfill only from recorded evidence.
ALTER TABLE review_runs ADD COLUMN model TEXT;
ALTER TABLE discussion_turns ADD COLUMN model TEXT;
UPDATE review_runs SET model = (
  SELECT model FROM model_calls WHERE operation = 'review' AND subject_id = review_runs.id
  ORDER BY started_at DESC, rowid DESC LIMIT 1
);
UPDATE discussion_turns SET model = (
  SELECT model FROM model_calls WHERE operation = 'discussion' AND subject_id = discussion_turns.id
    AND attempt = discussion_turns.attempt
  ORDER BY started_at DESC, rowid DESC LIMIT 1
);
