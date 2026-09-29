# Data and API contracts

## Scope clarification and design status

The assignment author's clarification, supplied by the developer, says that discussion should ideally be a follow-up conversation with the AI. The developer has agreed to include **per-finding AI conversation** in the MVP. The author accepts either applying fixes or recording acceptance only; this project keeps acceptance as a persisted finding resolution, without changing source code.

The snippet, review, finding-resolution, and per-finding conversation contracts below are implemented. Conversations extend the React + FastAPI + SQLite application and use the configured OpenAI provider.

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

Finding resolution: `open | accepted | dismissed`. Accept means acknowledge the finding, not apply a patch. The update endpoint sets a resolution idempotently and allows reopening via `open`. It only changes that finding; across clients, the last write wins.

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

All endpoints below are implemented.

| Method | Path | Contract |
| --- | --- | --- |
| POST | /api/snippets | `{ title, language, code }` -> 201 Snippet |
| GET | /api/snippets | Optional `language`, `reviewStatus`; -> `{ snippets: [...], languages: [...] }`; latest review status per row; languages across the workspace |
| GET | /api/snippets/:id | -> `{ snippet, latestReview: ReviewRun \| null }` |
| GET | /api/snippets/:id/reviews | -> `{ reviews: ReviewRun[] }`, newest first by `created_at DESC, rowid DESC`; unknown snippet -> 404 |
| POST | /api/snippets/:id/reviews | -> 202 ReviewRun; 409 if an active review exists |
| GET | /api/reviews/:id | -> `{ review, findings }`; polling source |
| PATCH | /api/findings/:id | `{ resolution }` -> updated Finding |

Error envelope: `{ error: { code, message } }`. Validation failures use 400, unknown IDs use 404, and an already active review uses 409. Missing OpenAI configuration uses 503 without creating a run. Unexpected server failures use 500 with a safe message. Provider failures are recorded on the asynchronous review and returned through the review endpoint. No provider SDK or key is bundled into the browser.

## Per-finding AI conversation

### User experience and boundaries

- Each finding has a **Discuss** button that opens the selected conversation in a wide workspace below the code/finding panels. Closing it returns focus to the finding; unsent drafts are retained in browser session storage when available. Users can ask for an explanation, an example, a possible false positive, or a revised fix.
- Show the user's question and the AI's answer in chronological order. Display pending, failed, and retry states alongside the relevant question. Conversation history survives page reloads and application restarts.
- The composer is disabled while that finding has an active reply. Other findings remain usable, and users can collapse the conversation or navigate away while a reply is being generated.
- Accept, dismiss, and reopen remain available independently of discussion. Users may discuss resolved findings. Sending a message does not change resolution, and changing resolution does not clear history.
- AI responses are explanations and suggestions only. They cannot edit source code, change the original finding, change review status, or accept/dismiss on the user's behalf. Display answer text with preserved whitespace; rich Markdown and streaming are outside this milestone.
- Re-review creates new findings with empty conversations. Old conversations remain attached to their original finding and review. No conversation is copied or matched across runs; the Review history selector can reopen the original review and conversation. Selection persists as the `review` query parameter; a review outside the snippet’s history is rejected by the UI.

### Data ownership and persistence

```text
Snippet
  └─ ReviewRun
       └─ Finding
            └─ DiscussionConversation
            └─ DiscussionTurn (one user question + one AI reply attempt)
```

One finding has one or more conversations. `005_discussion_conversations.sql` adds `discussion_conversations(id, finding_id, created_at)` and assigns every existing turn to the original conversation, whose ID equals its finding ID. It rebuilds the turn table transactionally with a required `conversation_id` and a composite foreign key `(conversation_id, finding_id)` to prevent cross-finding assignments. Old question/answer content, IDs, attempts and timestamps remain unchanged. Earlier migration files are immutable.

**New conversation** creates a persisted empty conversation without a provider call; **Conversation** switches between histories. Each retains independent draft and uncertain-submission storage. The original conversation keeps the old storage keys to preserve pre-upgrade drafts. Selection is remembered in browser session storage. Creating a conversation uses a client UUID as its ID and idempotency key; after an uncertain response the UI replays the same key. No key is needed just to create a conversation. The API rejects new conversation creation while the finding has an active reply, but replay of an existing creation remains available. One active reply per finding still applies across all its conversations.

Persist each question and its reply together as a turn, rather than storing an unpaired user message and assistant message. This gives the reply a clear execution state and makes retries possible without duplicating the visible question. The UI projects a turn into user/assistant chat bubbles.

| Field | Contract |
| --- | --- |
| id | Server-generated UUID |
| findingId | Foreign key to the owning finding; required |
| conversationId | Required owning conversation; must belong to the same finding |
| clientRequestId | Client-generated UUID for idempotent submission |
| userMessage | Nonblank question, up to 4,000 Unicode code points |
| assistantMessage | Nullable plain text; required and nonblank only on success |
| status | `queued`, `running`, `succeeded`, or `failed` |
| attempt | Positive integer, initially 1; increments on an explicit retry |
| createdAt | Creation time of the original question; unchanged by retry |
| startedAt / finishedAt | Timestamps for the current attempt |
| error | Safe user-facing error text on failure; otherwise null |

Invariants:

- A partial unique index on `finding_id` permits at most one queued/running turn per finding. A unique constraint on `(finding_id, client_request_id)` prevents duplicate submissions.
- Repeating the same request ID with the same question and conversation returns the existing turn without another provider call. Reusing it with different text or a different conversation returns 409. The client preserves its request ID after an uncertain network result and uses a new one for a new question.
- Use the review state-shape rules for timestamps/errors. Successful turns have an answer and no error; queued/running/failed turns have no answer. An empty or missing AI answer is a failure, not a completed chat turn.
- Order turns by `created_at, rowid`. Keep complete history in SQLite. No pagination is required for this local MVP.
- Save the answer and successful state atomically. Completion writes must match both the turn ID and current attempt number so a stale attempt cannot overwrite a retry.

### Context sent to the AI

For each reply, construct context on the server from:

1. The immutable snippet's code and language, with original source line numbers.
2. The selected finding's line range, severity, category, description, and suggested fix.
3. Up to the 10 most recent successful question/answer turns from the selected conversation preceding the current turn, followed by the new question. A new conversation sends no earlier exchanges, even from the same finding.

The prompt scopes the assistant to this finding and its snippet, permits it to explain uncertainty or acknowledge a false positive, and treats source code/comments as data. The server loads context through the finding's relationships; clients cannot provide replacement source code, arbitrary system prompts, or another finding's history.

Failed or incomplete turns are retained in the UI but excluded from model context. Older successful turns remain visible even when outside the context window; the conversation UI should state that the AI uses the most recent 10 exchanges. Keep the full source/finding context in each request and avoid relying on provider-side conversation IDs. Use the configured model and server-side key, disable automatic provider retries, and request no response storage using the existing API option. Bound replies to 1,500 output tokens; treat truncation, refusal, and empty output as explicit failures.

### Execution, failure, and retry

- Persist a queued turn before scheduling work, then return immediately. Reuse the application's in-process task execution pattern and share a two-call concurrency limit across review and conversation calls. This remains a single-backend-process design.
- Apply the configured timeout to the whole reply attempt, including time waiting for a concurrency slot. The frontend polls every two seconds while a turn is active and restores state through GET after reload.
- A lost submission response can be retried with the same `clientRequestId` to recover the persisted turn. A known failed generation uses the explicit retry endpoint.
- Only the latest failed turn in the selected conversation may be retried in place. Reset its answer/error and attempt timestamps, increment `attempt`, and keep its question, ID, and ordering. The retry request supplies the failed attempt number; stale/repeated retry requests return 409 rather than starting another call, and the client reloads state.
- Users may ask a new question after a failure; failed exchanges do not enter model context. If a later question already exists, offer to copy/rephrase the old failed question as a new turn instead of retrying it out of order.
- Shutdown cancels unfinished replies, and startup marks interrupted queued/running turns as failed with a retry message. Preserve the question and earlier answers. Provider/network errors use safe messages without exposing credentials, provider payloads, or stack traces.

### Discussion HTTP surface

These endpoints are implemented and use the existing camelCase conventions and error envelope.

| Method | Path | Request / response |
| --- | --- | --- |
| GET | /api/findings/:id/discussion | Optional `conversationId` query (defaults to original); 200 `{ conversationId, conversations, hasActiveReply, turns }`; turns belong only to that conversation, active flag covers the finding |
| POST | /api/findings/:id/conversations | `{ clientRequestId }` -> 201 new `DiscussionConversation`, 200 for a replay; no model call |
| POST | /api/findings/:id/discussion | `{ message, clientRequestId, conversationId? }` -> 202 DiscussionTurn (omitting conversationId selects the original) for a new queued turn; 200 for an identical idempotent replay |
| POST | /api/discussion-turns/:id/retry | `{ attempt }` -> 202 DiscussionTurn with incremented attempt |

Use 400 for invalid input; 404 for an unknown finding/turn; 409 for an active reply, conflicting request ID, or invalid/stale retry; and 503 for missing provider configuration without creating work. Generation failures are persisted and surfaced through the discussion GET endpoint.

### Acceptance criteria

1. Ask two follow-up questions about a finding; the second reply can use the first exchange. Create a new conversation on that finding and verify its first reply has no earlier chat context. Switch back and continue the original. Different findings and different conversations never share chat history.
2. Refresh while generating a reply and after completion. The question, progress/failure state, and saved answers remain recoverable. Restart recovery preserves history and permits retry.
3. Accept/dismiss/reopen before or during discussion. Conversation history, code, and review state remain intact.
4. Double-submit the same request ID and test a lost-response retry. Only one turn and one provider call are created. A different simultaneous question is rejected while a reply is active.
5. Simulate timeout, refusal, incomplete/empty output, and provider failure. No failure is displayed as a successful answer; retry does not duplicate the question, and stale completion cannot overwrite the new attempt.
6. Re-review the snippet. New findings start with no chat history; old turns stay attached to their original finding. Existing snippet/review/finding tests continue to pass.
7. Verify context isolation, the recent-10-exchange limit, safe answer rendering, and a real short follow-up conversation. Automated provider tests use mocks; live checks are small and explicit.

### Verification record

The 56-test suite includes mocked discussion/provider checks for follow-up history, finding isolation, the recent-10 context window, idempotent replay, conflicts, invalid input, missing configuration, provider failures, empty replies, refusal/truncation, queue timeout, guarded retries, restart recovery, and unchanged snippet/resolution behavior. Typecheck and production build pass. Browser checks cover a real two-turn conversation on the synthetic average snippet, persisted history, resolution independence, lost-response recovery across reload, failed-reply retry, separate finding history, and literal HTML-safe rendering. The failure checks use an isolated fake provider; only the two short successful follow-ups call OpenAI.

## Model-call diagnostics

`003_model_calls.sql` adds local call spans, keyed by operation, subject ID and attempt. They intentionally do not contain code, prompt bodies, user messages, assistant text or exception bodies. Model-call spans are diagnostic records rather than review/finding state; timing excludes queue wait. See [quality.md](quality.md#local-model-call-tracing) for fields, failure behavior, commands and limitations.


## Human evaluation annotations

This is an evaluation workflow separate from product finding resolution. Migration `004_quality_annotations.sql` adds `quality_sessions` and append-only `quality_annotations`. A session identifies a reviewer name and source hash, stores immutable copies of the dataset, report and normalized case/run outputs, and retains their hashes. `(source_id, reviewer)` is unique; starting the same session resumes it. A reviewer name is not an authenticated identity.

Each case annotation records independent observations, visible/unknown input assumptions, reference verdict/reason, proposed reference corrections, per-run/per-finding judgments, and per-run coverage/reasons. Case membership and run/finding indexes are checked against the frozen source, not mutable files. Drafts can be partial. Completing requires every judgment and a selected reference/finding reason (or prior written evidence), but permits uncertainty. All prose fields, including proposed corrections and coverage notes, are optional. The additive `independentVerdict`, `contractClarity`, `referenceReason`, and finding `reason` fields default to pending for older records. Reason enums must agree with their verdict on completion; drafts may be partial. Existing text-only annotations remain valid, with no backfill or changes to history. Missing suggestions require a Not applicable fix rating; failed calls cannot be marked as successful coverage. Reference corrections remain separate from original labels and require explicit future adjudication.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /api/quality/catalog | Available built-in/local result sources, unavailable snapshots and saved session progress |
| POST | /api/quality/sessions | `{sourceId, reviewer}` creates/resumes a frozen annotation session |
| GET | /api/quality/sessions/:id | Frozen cases/results plus latest saved annotations |
| PUT | /api/quality/sessions/:id/cases/:caseId | Replace this case's assessment with `{revision, status, ...}`; append a new revision |
| GET | /api/quality/sessions/:id/export | Download original evidence, metadata, latest annotations and all revision history |

Writes use a transaction and compare the client's revision with the latest stored revision (initial revision 0). A stale write returns 409 without changing prior records. All completed fields are validated server-side. Browser drafts are tab-local recovery only; exports contain saved revisions. Export reads the history and current state from one SQLite snapshot. No evaluation annotation makes a provider call, edits source code, changes a product finding's acceptance, mutates reference files, or automatically converts heuristic scores into human accuracy metrics. OpenAPI-derived types cover the annotation contracts.
