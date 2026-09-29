# Code Snippet Reviewer

A local React application for submitting code snippets to an LLM and resolving individual review findings.

Create and browse snippets, request an OpenAI review, inspect findings beside highlighted code, accept/dismiss or reopen them, and discuss each finding with the AI. Review state, resolutions, and conversations persist across reloads. The original MVP passed clean-clone setup and production-startup verification. It now also includes review history, a wide discussion workspace, sample code, browser regression tests, local model-call tracing, and a reproducible review-quality evaluation; see the [verification record](docs/verification.md) and [quality guide](docs/quality.md).

## Run locally

Prerequisites: Node.js 22.12+, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is selected by `.python-version`; uv can provision it if needed. Run commands from this repository directory.

```sh
npm run setup && npm run dev
```

Open http://127.0.0.1:5173. The API runs on http://127.0.0.1:3001. Both processes stop together when either exits. On startup the API creates `data/reviewer.db` and applies pending migrations. No database service is needed. Snippet management works without an API key; reviews and discussion require the configuration below.

Before requesting an AI review, copy `.env.example` to `.env` (`cp .env.example .env`) and set `OPENAI_API_KEY` to enable reviews and discussion. `OPENAI_MODEL` defaults to `gpt-4.1-mini`; `REVIEW_TIMEOUT_SECONDS` defaults to 60. Restart the backend after changing `.env`. You can also change the API port or database path. The Vite proxy follows the configured API port. The development proxy connects over loopback; keep the default `HOST` for local development. Secrets and database files are excluded from Git.

Build and run a single application process:

```sh
npm run build && npm start
```

Then open http://127.0.0.1:3001. The Python API serves the built React application. Keep the `migrations/` directory alongside the project when running the build.

## Commands

| Command | Purpose |
| --- | --- |
| `npm run setup` | Install Node and Python dependencies from lockfiles |
| `npm run dev` | React development server and API with reload |
| `npm run db:migrate` | Initialize or migrate the file database explicitly |
| `npm run api:types` | Regenerate frontend types from the Python API schema |
| `npm run typecheck` | Check frontend TypeScript |
| `npm test` | Database, API lifecycle, mocked provider, tracing, and evaluation-grader tests |
| `npm run test:e2e` | Build and run isolated desktop/narrow-screen browser workflows |
| `npm run eval:review -- --live` | Opt-in billable review-quality evaluation on synthetic cases |
| `npm run trace:calls` | Inspect recent local model-call metadata |
| `npm run build` | Typecheck and build frontend |
| `npm start` | Serve the built application and API |
| `npm run check` | Run typecheck, tests, and build |

For browser tests, install the test browser once with `npx playwright install chromium`, then run `npm run test:e2e`. These tests use a temporary SQLite database and deterministic providers on port 3032; no OpenAI key or API calls are used.

## Architecture

```text
React + TypeScript + Vite ── /api ── FastAPI + Pydantic ── SQLite file
```

- React with TypeScript handles the client; Python with FastAPI handles the API, following the developer's backend preference. Vite handles frontend development and builds.
- FastAPI exposes the implemented API schema at `/openapi.json` and interactive docs at `/docs`. Pydantic is the source of truth for backend domain validation. Frontend API types are generated from OpenAPI with `npm run api:types` and committed in `src/shared/api-types.ts`. Regenerate them after changing endpoint models.
- SQLite uses Python's standard `sqlite3` module, avoiding a separate database service and native Node addons. Connections are scoped to each operation. Reads use regular FastAPI handlers; asynchronous task runners perform short SQLite transactions before and after provider calls.
- Numbered SQL migrations are transactional and recorded with checksums. Applied migrations are immutable; add a new file for a schema change.
- `Snippet`, `ReviewRun`, `Finding`, and `DiscussionTurn` have separate persistence and lifecycles. Partial unique indexes prevent two active reviews per snippet or two active replies per finding; request IDs deduplicate question submissions.
- SQL constraints protect persisted enum values, foreign keys, review state shape, and basic line ranges. Pydantic validation additionally checks line references against the actual code.
- `package-lock.json` and `uv.lock` pin dependencies. The production startup serves the React build from one Python backend process.

See [data and API contracts](docs/data-contract.md) for invariants and implemented endpoints, and [execution plan](docs/execution-plan.md) for the completed milestones and scope boundaries.

## Design decisions and open scope

- Snippets are immutable in the MVP; changing code means creating a new snippet.
- Accept/dismiss records a finding's resolution and does not modify code.
- Each rerun creates a new review and findings. The latest review drives the dashboard; old resolutions are not copied.
- Background reviews run as asynchronous tasks in a single local backend process, with persisted status and frontend polling. Startup marks interrupted queued/running reviews as failed; retry creates a new run. Run only one backend process against a database: multiple workers require ownership leases and a durable task runner.
- The assignment author clarified that discussion should ideally be follow-up conversation with the AI. This is implemented in the MVP: per-finding chat, persistent history, snippet/finding context, and failure/retry handling. The author also accepts recording acceptance without automatically applying fixes, matching this project's behavior. See the [conversation design](docs/data-contract.md#per-finding-ai-conversation).
- OpenAI credentials are server-only and excluded from settings serialization. Provider exception bodies are not stored in findings, returned to clients, or logged by the runner.

## Snippet management

- Create a snippet with a title, language, and nonblank code (up to 100,000 Unicode code points). Code is stored without trimming or changing line endings.
- The language picker supports Python, TypeScript, JavaScript, Go, Rust, Java, C++, SQL, and plain text. Unknown API-submitted languages safely fall back to plain text display.
- Dashboard filters combine with AND semantics and use the latest review, not an older matching run. The language menu lists languages across the workspace even when filters return no rows.
- Hash-based routes preserve detail URLs and filters on refresh without requiring SPA fallback rules on the Python static server.
- Code is escaped by the highlighter and is never executed. Line endings are normalized only for display.
- Step 2 validation: 16 automated tests, TypeScript/build checks, and browser checks for creation, code highlighting, reload, and filtering.

## AI reviews

1. Open a snippet and choose **Review snippet**. Its code and language are sent to OpenAI. No repository files or title are sent.
2. The API persists a queued run and immediately returns 202. Reviews and discussion replies share two concurrent provider slots, with one active review per snippet and one active reply per finding. The total time limit includes queue wait. SDK automatic retries are disabled; users explicitly retry failures.
3. The backend uses the [Responses API with structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), validates the schema and source line bounds, and saves all findings plus successful completion in one SQLite transaction. `store=False` disables response storage through this API option; it is not a claim of zero provider retention.
4. Refusal, incomplete output, invalid findings, timeout, authentication, quota, and provider errors are failures, not successful empty reviews. A completed empty findings array is a valid result.
5. Active detail/list views poll every two seconds. Reloading restores persisted state. Graceful shutdown cancels unfinished tasks; abrupt process interruption is recovered on next startup. The **Review history** selector restores earlier runs, resolutions, and discussions. The selected run is encoded in the URL and survives reload; dashboard status still reflects the latest run.

Default model: [`gpt-4.1-mini`](https://developers.openai.com/api/docs/models/gpt-4.1-mini), configurable through `.env`. Responses and severity judgments remain model-generated suggestions; broader quality evaluation and severity calibration are future work.

Validation: 72 automated backend/grader/annotation tests and 16 desktop/narrow browser workflow cases (mocked provider, no API cost), frontend typecheck/build, a successful real provider smoke test, and a browser-triggered real review of a synthetic averaging function. The real review found a division-by-zero edge case on line 2. The test suite currently emits one upstream Starlette/httpx deprecation warning.

## Finding interaction

- Choose a finding's line reference to scroll to and highlight its inclusive source range. The entire snippet is highlighted as one unit, preserving multi-line strings and comments; a separate overlay marks the selected lines. **Clear highlight** removes the selection.
- **Accept** acknowledges an issue; it does not apply the suggested fix. **Dismiss** records that the finding is not being acted on. **Reopen** returns it to open. Resolved findings remain visible.
- Buttons show a pending state while saving. UI state changes only after the backend confirms the update; failed writes preserve the previous state and show an error. The count of open findings updates immediately after successful saves.
- Each mutation affects one finding. Source code, review execution status, other findings, and findings from earlier/later runs are unchanged. Repeated writes of the same state are idempotent. Multiple clients use last-write-wins semantics; version conflict detection is outside this local MVP.
- Browser checks verified accept/dismiss persistence after reload, reopen, single-line and off-screen multi-line selection, and failed-write behavior against an isolated test server. These checks did not make additional OpenAI calls.

## Finding discussion

- Choose **Discuss with AI** on any finding, including accepted or dismissed ones. A wide discussion workspace opens below the code and findings; closing it restores keyboard focus and retains the draft in session storage when available. Ask a question or follow up on a previous answer. The UI shows queued/running progress, disables that composer while generating, and polls every two seconds. Other finding actions remain available.
- Each request includes the full numbered snippet, the selected finding, and up to 10 recent successful exchanges from that finding only. All exchanges remain saved locally. The implementation follows OpenAI's [manual conversation history](https://developers.openai.com/api/docs/guides/conversation-state) approach; it uses plain text, no streaming, `store=False`, and a 1,500-token reply limit.
- **Retry reply** retries the latest failed turn in place. Earlier failed questions can be copied into the composer with **Use question again**. Failures stay visible but are excluded from AI context. Retries preserve question IDs and increment an attempt number; stale completions cannot overwrite a newer attempt.
- A client request ID prevents duplicate submissions. An uncertain submission keeps its exact question and ID in session storage (or memory if storage is unavailable). After a lost response or reload, **Check submission** recovers the persisted turn without making another AI call. Explicit provider retries are separate from submission recovery.
- Resolution changes do not affect conversation history, and replies cannot change source code or finding status. A new review creates new findings with empty conversations; older conversations remain accessible through the review-history selector and API.
- Shutdown/startup recovery marks interrupted replies failed without losing saved questions. The same configured timeout bounds both queue wait and generation. Only one backend process may own a database.
- Browser verification used two short real follow-ups on the averaging example. An isolated fake-provider server verified a lost POST response plus reload/recovery, failed-reply retry without duplicate questions, finding isolation, and HTML displayed as literal text. No real API calls are made by automated tests.

## Examples, evaluation, and diagnostics

The new-snippet form offers Python and TypeScript sample code. Examples fill only an empty form, never overwrite a draft, and make no automatic API call. Save the snippet, then explicitly request its review.

The default `review-v2` prompt was selected after comparing three versions against a fixed ten-case development dataset. Severity agreement improved, but speculative findings on correct SQL remain a known limitation. Raw synthetic reports and prompt snapshots are committed under `evals/`; metric definitions, results, limitations, manual grading, and run commands are in [quality.md](docs/quality.md). These scores are regression indicators, not general accuracy claims.

Open **Human review** in the header (or `/#/quality`) to annotate existing eval results. Choose `candidate-v2` and enter your name. Select your code assessment, validate the reference, then grade each finding and check coverage for both runs. Common reasons are selectable and all written notes are optional, including proposed reference corrections. Save drafts or complete a case to persist progress in SQLite; export includes original evidence and revision history. No new AI calls are made. See the [step-by-step annotation guide](docs/quality.md#human-annotation-workspace).

Local model-call spans record model/prompt version, job ID/attempt, timing, available token usage, provider IDs and failure class. They do not duplicate source, messages, replies, exception bodies, or API keys. View them with `npm run trace:calls`; calls made before this feature are not backfilled. See [tracing details](docs/quality.md#local-model-call-tracing).

## What I would change with more time

For deployment beyond a single local process, introduce a durable job worker with leases/recovery, address authentication and data ownership, and review database concurrency needs. Add snippet revisions before allowing edits and extend quality evaluation to independently labeled, representative held-out snippets. Prioritize these only when their use cases justify the added complexity.

## AI usage log

Development uses Codex. [AI_USAGE.md](AI_USAGE.md) records five concrete examples, the developer’s decisions, observed corrections, validation, and an overall assessment. [The demo guide](docs/verification.md#short-demo) walks through the main workflow.
