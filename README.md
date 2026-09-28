# Code Snippet Reviewer

A local React application for submitting code snippets to an LLM and resolving individual review findings.

**Current milestone: steps 3–4, real AI reviews and review lifecycle.** Create and browse snippets, trigger an OpenAI review, follow its progress, and inspect saved findings beside highlighted code. Retry, rerun, timeout handling, and interrupted-run recovery are implemented. Accept/dismiss and clickable line navigation are the next milestone.

## Run locally

Prerequisites: Node.js 22.12+, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is selected by `.python-version`; uv can provision it if needed. Run commands from this repository directory.

```sh
npm run setup && npm run dev
```

Open http://127.0.0.1:5173. The API runs on http://127.0.0.1:3001. Both processes stop together when either exits. On startup the API creates `data/reviewer.db` and applies pending migrations. No database service is needed. Snippet management works without an API key; reviews require the configuration below.

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` to enable reviews. `OPENAI_MODEL` defaults to `gpt-4.1-mini`; `REVIEW_TIMEOUT_SECONDS` defaults to 60. Restart the backend after changing `.env`. You can also change the API port or database path. The Vite proxy follows the configured API port. The development proxy connects over loopback; keep the default `HOST` for local development. Secrets and database files are excluded from Git.

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
| `npm test` | Database, validation, and API foundation tests |
| `npm run build` | Typecheck and build frontend |
| `npm start` | Serve the built application and API |
| `npm run check` | Run typecheck, tests, and build |

## Architecture

```text
React + TypeScript + Vite ── /api ── FastAPI + Pydantic ── SQLite file
```

- React with TypeScript handles the client; Python with FastAPI handles the API, following the developer's backend preference. Vite handles frontend development and builds.
- FastAPI exposes the implemented API schema at `/openapi.json` and interactive docs at `/docs`. Pydantic is the source of truth for backend domain validation. Frontend API types are generated from OpenAPI with `npm run api:types` and committed in `src/shared/api-types.ts`. Regenerate them after changing endpoint models.
- SQLite uses Python's standard `sqlite3` module, avoiding a separate database service and native Node addons. Connections are scoped to each request; synchronous database work runs in regular FastAPI handlers.
- Numbered SQL migrations are transactional and recorded with checksums. Applied migrations are immutable; add a new file for a schema change.
- `Snippet`, `ReviewRun`, and `Finding` have separate persistence and lifecycles. A partial unique index prevents two active reviews for one snippet, even across database connections.
- SQL constraints protect persisted enum values, foreign keys, review state shape, and basic line ranges. Pydantic validation additionally checks line references against the actual code.
- `package-lock.json` and `uv.lock` pin dependencies. The production startup serves the React build from one Python backend process.

See [data and API contracts](docs/data-contract.md) for invariants and planned endpoints, and [execution plan](docs/execution-plan.md) for the remaining milestones.

## Design decisions and open scope

- Snippets are immutable in the MVP; changing code means creating a new snippet.
- Accept/dismiss records a finding's resolution and does not modify code.
- Each rerun creates a new review and findings. The latest review drives the dashboard; old resolutions are not copied.
- Background reviews run as asynchronous tasks in a single local backend process, with persisted status and frontend polling. Startup marks interrupted queued/running reviews as failed; retry creates a new run. Run only one backend process against a database: multiple workers require ownership leases and a durable task runner.
- Discussion is pending clarification: the overview mentions it, but the detailed requirements do not define comments versus AI conversation.
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
2. The API persists a queued run and immediately returns 202. Up to two reviews can execute concurrently, with one active run per snippet. The total time limit includes queue wait. SDK automatic retries are disabled; users explicitly retry failures.
3. The backend uses the [Responses API with structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), validates the schema and source line bounds, and saves all findings plus successful completion in one SQLite transaction. `store=False` disables response storage through this API option; it is not a claim of zero provider retention.
4. Refusal, incomplete output, invalid findings, timeout, authentication, quota, and provider errors are failures, not successful empty reviews. A completed empty findings array is a valid result.
5. Active detail/list views poll every two seconds. Reloading restores persisted state. Graceful shutdown cancels unfinished tasks; abrupt process interruption is recovered on next startup. Terminal runs and their findings remain available through the API, although there is no history selector yet.

Default model: [`gpt-4.1-mini`](https://developers.openai.com/api/docs/models/gpt-4.1-mini), configurable through `.env`. Responses and severity judgments remain model-generated suggestions; broader quality evaluation and severity calibration are future work.

Validation: 29 automated tests (mocked provider, no API cost), frontend typecheck/build, a successful real provider smoke test, and a browser-triggered real review of a synthetic averaging function. The real review found a division-by-zero edge case on line 2. The test suite currently emits one upstream Starlette/httpx deprecation warning.

## What I would change with more time

For deployment beyond a single local process, introduce a durable job worker with leases/recovery, address authentication and data ownership, and review database concurrency needs. Add snippet revisions before allowing edits, expose review history, and evaluate review quality against representative snippets. Prioritize these only when their use cases justify the added complexity.

## AI usage log

Development uses Codex. The ongoing record in [AI_USAGE.md](AI_USAGE.md) distinguishes generated work, design decisions, observed corrections, and validation. It will be completed with 3–5 concrete examples and an overall assessment as implementation proceeds.
