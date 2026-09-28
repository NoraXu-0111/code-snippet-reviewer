# Code Snippet Reviewer

A local React application for submitting code snippets to an LLM and resolving individual review findings.

**Current milestone: step 2, snippet management.** Create snippets, browse the dashboard, filter by language/review status, and open read-only code with syntax highlighting and line numbers. AI calls, review execution, and finding interactions are not implemented yet.

## Run locally

Prerequisites: Node.js 22.12+, npm, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is selected by `.python-version`; uv can provision it if needed. Run commands from this repository directory.

```sh
npm run setup && npm run dev
```

Open http://127.0.0.1:5173. The API runs on http://127.0.0.1:3001. Both processes stop together when either exits. On startup the API creates `data/reviewer.db` and applies pending migrations. No database service or AI key is needed for this milestone.

Configuration is optional: copy `.env.example` to `.env` to change the API port or database path. The Vite proxy follows the configured API port. The development proxy connects over loopback; keep the default `HOST` for local development. Secrets and database files are excluded from Git.

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
- Planned background execution is within the local backend process, with persisted status and frontend polling. Restart recovery and retry will be implemented in the review milestone; they do not exist yet.
- Discussion is pending clarification: the overview mentions it, but the detailed requirements do not define comments versus AI conversation.
- OpenAI is the selected LLM provider. Put `OPENAI_API_KEY` in the ignored local `.env` file; credentials are server-only and excluded from settings serialization. The model and review timeout remain to be selected during integration. Restart the API after changing `.env`. This milestone does not make OpenAI API calls yet.

## Snippet management

- Create a snippet with a title, language, and nonblank code (up to 100,000 Unicode code points). Code is stored without trimming or changing line endings.
- The language picker supports Python, TypeScript, JavaScript, Go, Rust, Java, C++, SQL, and plain text. Unknown API-submitted languages safely fall back to plain text display.
- Dashboard filters combine with AND semantics and use the latest review, not an older matching run. The language menu lists languages across the workspace even when filters return no rows.
- Hash-based routes preserve detail URLs and filters on refresh without requiring SPA fallback rules on the Python static server.
- Code is escaped by the highlighter and is never executed. Line endings are normalized only for display.
- Step 2 validation: 16 automated tests, TypeScript/build checks, and browser checks for creation, code highlighting, reload, and filtering.

## What I would change with more time

For deployment beyond a single local process, introduce a durable job worker with leases/recovery, address authentication and data ownership, and review database concurrency needs. Add snippet revisions before allowing edits, expose review history, and evaluate review quality against representative snippets. Prioritize these only when their use cases justify the added complexity.

## AI usage log

Development uses Codex. The ongoing record in [AI_USAGE.md](AI_USAGE.md) distinguishes generated work, design decisions, observed corrections, and validation. It will be completed with 3–5 concrete examples and an overall assessment as implementation proceeds.
