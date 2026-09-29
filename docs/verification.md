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


### Follow-up: selection-based annotation

The user found mandatory prose difficult, so the workflow now offers explicit choices for independent assessment, input clarity and reference/finding reasons; all written notes and proposed corrections are optional. Reasons are stored as structured codes, not generated evidence, and changing a verdict clears its selected reason. Existing annotations and drafts remain compatible. `npm run check` passes with 72 backend tests and the frontend build. All four annotation browser cases pass across desktop/narrow widths; they complete a case without writing any notes, export the selected reason codes with empty prose, restore saved choices, verify stale-write protection, and load prior partial/text-only drafts. No new model calls were made. The unchanged ten product workflow browser cases retain their prior passing result.


### Follow-up: blocked completion button

The user reported being unable to click Complete after saving first-step drafts. The footer previously disabled Complete until outputs were revealed, without a next-step action. It now offers Continue to reference, Continue to model outputs, then Complete; step progress is visible and navigation focuses the relevant heading. Missing prerequisite answers display an explanation at the focused step. Saved answers, revisions and completion semantics are unchanged. Read-only inspection confirmed ten user drafts exist; no user annotations were modified during this fix. Frontend typecheck/build and six desktop/narrow annotation browser cases pass, including a new saved-draft continuation regression, missing-answer guidance, focus/viewport checks, and verification that Continue does not write or mark a case completed. The unchanged ten product browser cases and 72 backend tests retain their prior passing results.

## Independent conversations per finding

During the user's manual end-to-end walkthrough, groups 1–3 (snippet management, review/display, finding resolution/history) were reported passing. Group 4 (discussion) prompted a request to start a fresh conversation on the same finding. Added New conversation and a persisted-history selector, with per-conversation context, drafts and pending submissions. Empty conversation creation is keyless and does not invoke the model. A lost creation response recovers via the same client UUID. The finding still permits only one active reply at a time; retries target the latest failed turn within the selected conversation.

Validation: the production build/typecheck and all 77 backend tests pass. After reserving original finding IDs against client ID collisions, the five conversation tests passed again. All 20 browser cases pass at desktop/narrow widths, including independent same-finding histories, old/new drafts, reload selection, legacy reply recovery and lost conversation-creation recovery. The default test port was occupied, so this run used `E2E_PORT=3037` without stopping or reusing another server. A configurable isolated test port is now supported.

Before migration, the local database was backed up under ignored `data/backups/`. Comparing all four pre-existing discussion turns after migration confirmed their previous fields are unchanged and they belong to their original conversations; SQLite integrity check returned `ok`. A separate migration test also verifies preservation of answers/resolution and foreign-key enforcement. No user annotation answers were changed and no real model calls were made for this feature. User manual confirmation of the expanded discussion workflow remains pending.


## Independent review repairs — September 28, 2026

Addressed all three findings from the independent review of `74d1f3b`:

- **Delayed annotation saves:** callbacks from an unmounted case editor cannot clear browser storage, update session state, or navigate. Successful saves clear only the submitted draft; reverting edits clears only that editor's last stored draft. Browser regression forwards a PUT, delays its successful response, leaves/returns to the case, writes newer evidence, then delivers the old response. The newer draft survives another navigation and reload; the server retains the original saved evidence and revision. Normal draft reversion is also covered.
- **Uncertain review submissions:** migration 006 atomically maps a required client request UUID and snippet to a run. Replays return that run at any execution status, including after restart without an API key. The browser retains the UUID in session storage until confirmation and offers Check submission; only a subsequent intentional new review gets another UUID. Desktop and narrow tests drop a persisted POST response, wait for completion, recover both with and without reload, and verify one run and exactly one mock provider invocation. An explicit new review is then verified to create a different request ID and a second call. The call counter exists only in the temporary E2E server.
- **Review detail consistency:** status and findings share an explicit SQLite read transaction. A deterministic second-connection commit between the two SELECTs proves the response retains the old snapshot; the next read sees the completed result. Tests also cover caller-owned transactions and release of owned transactions on missing results/errors.

Validation: `npm run check` passed all **82 backend tests** plus TypeScript and production build. The full Playwright suite passed **26 desktop/narrow cases** on isolated port 3041. After refining normal draft reversion/cleanup and its regression, the frontend build and all **8 annotation browser cases** passed again on port 3042. Generated OpenAPI types were updated; `git diff --check` passed. The running development API's health and OpenAPI endpoints confirm the new required submission payload and replay response are loaded. Tests used temporary databases and mocked providers; no live provider calls or human annotation edits were made. The existing upstream Starlette/httpx deprecation warning remains.

Submission recovery is scoped to a retained client UUID, including same-tab reloads. Clearing browser storage discards that identity. This does not claim exactly-once execution at the remote provider after a crash. Existing run/finding rows are preserved by the additive mapping migration. Optional production-scale changes from the review remain outside this repair.
