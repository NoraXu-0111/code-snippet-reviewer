-- Separate submission identity preserves the shape of existing review runs.
CREATE UNIQUE INDEX review_run_snippet_identity ON review_runs(id, snippet_id);
CREATE TABLE review_submissions (
  snippet_id TEXT NOT NULL REFERENCES snippets(id) ON DELETE RESTRICT,
  client_request_id TEXT NOT NULL,
  review_run_id TEXT NOT NULL UNIQUE,
  PRIMARY KEY (snippet_id, client_request_id),
  FOREIGN KEY (review_run_id, snippet_id) REFERENCES review_runs(id, snippet_id) ON DELETE RESTRICT
) STRICT;
