# Data and API contracts

## Implemented foundation

IDs are application-generated UUIDs. Timestamps are UTC ISO 8601 strings. API fields use camelCase; SQL uses snake_case. One-based line references are inclusive. Submitted code retains its whitespace and line endings.

| Entity | Fields |
| --- | --- |
| Snippet | id, title, language, code, createdAt |
| ReviewRun | id, snippetId, status, createdAt, startedAt, finishedAt, error |
| Finding | id, reviewRunId, startLine, endLine, severity, category, description, suggestedFix, resolution |

Limits selected for this MVP: title 1–120 characters, language identifier 1–50, and nonblank code up to 100,000 Unicode code points at the API boundary. The UI offers Python, TypeScript, JavaScript, Go, Rust, Java, C++, SQL, and plain text; storage is not restricted to a language enum.

Severity: `critical | warning | info`. Category: `bug | style | performance | security`. These values are a project choice based on the assignment examples. `suggestedFix` is nullable text. LLM output omitting it normalizes to `null`.

Review state shape:

| Status | startedAt | finishedAt | error |
| --- | --- | --- | --- |
| queued | null | null | null |
| running | required | null | null |
| succeeded | required | required | null |
| failed | optional | required | nonblank |

Implemented transitions are `queued -> running -> succeeded/failed`, with `queued -> failed` allowed for interrupted startup or failure before execution. Terminal reviews are not restarted in place. A retry creates a new run. The initial migration enforces valid state shape; the task runner performs guarded transitions and marks interrupted tasks as failed during startup/shutdown.

Finding resolution: `open | accepted | dismissed`. Accept means acknowledge the finding, not apply a patch. The planned update endpoint sets a resolution idempotently and allows reopening via `open`.

Dashboard state derives from the latest review, independently of finding resolution:

| Latest review | Dashboard |
| --- | --- |
| None | not_reviewed |
| queued / running | in_progress |
| succeeded, including zero findings | reviewed |
| failed | failed |

SQLite permits at most one queued/running review per snippet. Reruns retain their own findings and resolutions. Application queries select the newest run by `created_at DESC, rowid DESC` to resolve timestamp ties deterministically within this SQLite MVP.

LLM output is `{ findings: [...] }`. Parse the entire object and check line bounds before persisting it. Review execution saves all findings and marks success in one transaction; invalid output is a failed review, never an empty successful review.

## HTTP surface

`GET /api/health` is implemented. Response: `{ "status": "ok", "database": "connected" }`.

Snippet and review endpoints below are implemented. Finding mutation remains planned.

| Method | Path | Contract |
| --- | --- | --- |
| POST | /api/snippets | `{ title, language, code }` -> 201 Snippet |
| GET | /api/snippets | Optional `language`, `reviewStatus`; -> `{ snippets: [...], languages: [...] }`; latest review status per row; languages across the workspace |
| GET | /api/snippets/:id | -> `{ snippet, latestReview: ReviewRun \| null }` |
| POST | /api/snippets/:id/reviews | -> 202 ReviewRun; 409 if an active review exists |
| GET | /api/reviews/:id | -> `{ review, findings }`; polling source |
| PATCH | /api/findings/:id | `{ resolution }` -> updated Finding |

Error envelope: `{ error: { code, message } }`. Validation failures use 400, unknown IDs use 404, and an already active review uses 409. Missing OpenAI configuration uses 503 without creating a run. Unexpected server failures use 500 with a safe message. Provider failures are recorded on the asynchronous review and returned through the review endpoint. No provider SDK or key is bundled into the browser.
