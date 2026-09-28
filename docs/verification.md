# Verification and demo guide

## Verification record

Verified on September 28, 2026 against implementation commit `6aa8794`. This section records the original clean-clone verification; the later improvement milestone is recorded below.

A fresh local Git clone was created outside the working repository. It did not contain the development `.env`, database, `node_modules`, `.venv`, or build output. Installations used the committed lockfiles; normal machine-level package caches were available. No OpenAI credentials were supplied to this clone.

Environment: macOS arm64, Node 25.6.1, npm 11.9.0, uv 0.11.7, Python 3.12.13. This is one tested environment, not a claim that all supported Node/Python versions or operating systems were tested.

| Check | Result |
| --- | --- |
| `npm run setup` | Passed: fresh Node dependencies and Python virtual environment installed from lockfiles |
| `npm run check` | Passed: TypeScript, production build, all 56 pytest cases |
| `npm run api:types` followed by `git diff --exit-code` | Passed: generated client contracts exactly match committed types |
| `npm start`, isolated port 3011 | Passed: built React files and API served by one Python process |
| Empty database and snippet creation in browser | Passed: empty state, create/detail, source display, metadata |
| Missing API key | Passed: clear configuration error; database confirms no review run created |
| Actual process stop/restart and browser reload | Passed: saved snippet and original code restored |
| Successful review with zero findings | Passed: seeded display fixture shows Reviewed / No issues found; no provider call used for this fixture |
| Git content review | Seven incremental commits inspected; `.env` and database files absent from tracked HEAD, `.env` absent from history, no common OpenAI-key/private-key patterns found in history |

The test suite emits one non-blocking upstream Starlette/httpx deprecation warning. This milestone made no additional live OpenAI requests. Earlier milestones verified a real review and two real follow-up replies; the developer also confirmed the conversation feature works.

## Coverage of the workflow

| Behavior | Evidence |
| --- | --- |
| Create/list/detail; language and latest-review filters; persistence | `tests/test_snippets.py`, earlier browser checks, fresh production smoke test |
| Validation, state shape, migrations, active-review uniqueness | `tests/test_foundation.py` |
| Async review, duplicate trigger, empty/invalid output, timeout, atomic findings, recovery | `tests/test_reviews.py` |
| Structured OpenAI request, refusal and incomplete output handling | `tests/test_openai_reviewer.py`; earlier real averaging-example review |
| Accept/dismiss/reopen and independence from source/review/other findings | `tests/test_findings.py`; earlier browser persistence and failed-write checks |
| Multi-turn context, isolation, recent-10 window, replay, guarded retries, queue timeout, restart recovery | `tests/test_discussions.py` |
| Discussion payload, provider errors, refusal/incomplete/empty reply handling | `tests/test_openai_discussion.py`; earlier real two-turn conversation |
| Lost-response recovery after reload; retry without duplicate question; safe literal rendering | Earlier browser checks against an isolated fake-provider server |

At this original milestone, browser checks were manual automation and model quality had only received a smoke test. The improvement milestone below supersedes those two limitations with a committed browser suite and small development-set evaluation. Concurrency verification targets the documented single-process local architecture.

## Short demo

Before presenting, set `OPENAI_API_KEY` in `.env`, restart the backend, and run `npm run setup && npm run dev`. A live demo makes billable provider calls using that key. To show existing results without another call, open the previously saved example in the development database.

1. Create a Python snippet titled **Average calculation**:

   ```python
   def average(values):
       return sum(values) / len(values)
   ```

2. Choose **Review snippet**. Show the pending state and completed findings. The empty-list division is a useful example, but exact wording and severity are model-dependent.
3. Select a finding's line reference to highlight its source. Inspect the suggested fix, then accept and reopen the finding. Explain that acceptance records a decision and does not edit code.
4. Choose **Discuss with AI**. Ask “What input causes this issue?” followed by “For that input, show a fix that raises ValueError.” Refresh and reopen the discussion to show persistence.
5. Return to the dashboard and filter by Python and Reviewed. Optionally run a new review to show that it creates new findings and conversations; doing so makes another API call.

## Delivery scope

The committed repository contains source, migrations, dependency lockfiles, tests, setup instructions, architecture/design decisions, and five concrete AI-usage examples. Local secrets, databases, temporary fixtures, dependency directories, and build output are excluded. Share the Git repository or a Git-preserving archive when submitting so reviewers can inspect the incremental history.

The MVP deliberately omits authentication, snippet edits/deletes, automatic fix application, streaming, rich Markdown chat, and a durable multi-process worker. Deployment or submission to an external destination has not been performed.

## Improvement milestone verification

- TypeScript includes browser test/config files; production build and 63 backend/grader tests pass.
- Five browser workflows run at 1280×900 and 390×844 (ten cases): review/resolution/discussion/rerun/history, generation failures/retries/draft retention, lost-response recovery across reload, zero findings/filtering, and sample-code/focus/width behavior. Eight passed on the first run; the two filter tests passed after correcting their locator. No app workaround or API call was used for that correction.
- Browser tests use the real FastAPI routes and a temporary SQLite file with deterministic provider adapters. `reuseExistingServer: false` avoids accidentally attaching to a development instance. The temporary server/database are cleaned up afterward.
- Tracing tests verify metadata-only writes, concurrent subject isolation, failures/cancellation/interruption, best-effort storage, and correlation through the real OpenAI adapters with mocked SDK responses.
- Ten synthetic evaluation cases were run 50 times in total across three prompt versions: v1 once, v2 twice, v3 twice. See [quality.md](quality.md) for the measurements, source reports, chosen version and known SQL false positive.
- The existing development snippet and its saved conversation were visually checked in the new wide workspace without rerunning the model. Historical results retain their original severity; prompt changes apply only to new reviews.

Install browser support with `npx playwright install chromium`; run `npm run check` and `npm run test:e2e` for software validation. Run `npm run eval:review -- --live` separately for billable model-quality evaluation. Browser trace artifacts may include synthetic test content; they are ignored by Git.

## Human annotation workflow verification — September 28, 2026

The user requested a practical human review workflow for the existing eval dataset. Added `/#/quality` with staged independent code inspection, reference validation, and per-run finding/coverage assessments. Sessions freeze their dataset and report; annotation revisions are append-only and reject stale writes. Drafts and completed assessments persist in SQLite, with tab-local unsaved recovery and a full saved-history JSON export. No human labels were filled in on the user's behalf and no provider calls were made for this milestone.

Validation: `npm run check` passes (69 pytest cases, frontend typecheck and production build). The full Playwright suite passes all 14 cases across desktop and narrow viewports. After hardening restoration of partial drafts written through the API, all four annotation browser cases passed again, including the added partial-draft scenario. New tests cover frozen source/hash validation, restart/export history, evidence requirements, invalid/cross-case indexes, optimistic revision conflicts, and coverage for empty/failed outputs. Initial annotation browser failures were caused by an exact `getByLabel` select locator; using the accessible combobox name resolved the test issue. Desktop landing and narrow assessment screenshots were visually inspected; no horizontal page overflow was observed. Test sessions used temporary databases and deterministic providers. The running development server exposes the new catalog; no test annotation session was created in the user's real workspace database.
