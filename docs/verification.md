# Tests, verification, and demo

## Current verification status

Latest verification covers OpenAI model selection, including GPT-5.5 and GPT-5.6 Sol: **90 backend tests and 30 browser cases passed**, along with TypeScript and production build. Generated API types include the model catalog and model fields. The earlier independent-review repairs were committed in `91c4fd5`; this milestone adds selection without weakening their replay/draft protections.

The browser suite has **15 scenarios run twice** in Chromium: desktop 1280 x 900 and narrow 390 x 844. It uses the real React app, FastAPI routes, a temporary SQLite database, and deterministic providers. Backend provider-adapter tests mock SDK responses. Automated checks do not call a paid model or modify the user's database. Failed browser tests retain screenshots and action/network traces under ignored `test-results/`.

## Run checks

```sh
npm run check
npx playwright install chromium  # First browser-test setup only.
npm run test:e2e
# Use an isolated alternate port if 3032 is occupied:
E2E_PORT=3037 npm run test:e2e
```

`npm run api:types` regenerates contracts; inspect the resulting diff when changing the API. `npm run eval:review -- --live` is a separate, billable quality evaluation, not part of the software test suite.

## Backend coverage

Counts include parametrized cases. All current backend test modules are listed here.

| Test module | Covered behavior |
| --- | --- |
| [test_foundation.py](../tests/test_foundation.py) | Persistence; repeatable and failed/rolled-back migrations; foreign keys, state/line constraints; active review uniqueness across connections; validation and JSON naming; API startup/health |
| [test_snippets.py](../tests/test_snippets.py) | Create/list/detail; invalid input; reload after app restart; language/latest-review filters and combinations; timestamp ties; unknown IDs and query validation |
| [test_reviews.py](../tests/test_reviews.py) | Async lifecycle; active submission conflicts; empty/invalid output; provider failure/timeout; atomic findings rollback; shutdown/startup recovery; missing configuration; required request UUID; replay after success/failure/restart without a key; per-snippet identity; consistent detail reads with concurrent completion and transaction cleanup |
| [test_models.py](../tests/test_models.py) | Configured/catalog defaults; selected models reaching real adapters with mocked SDKs, including GPT-5.5/GPT-5.6 Sol request options; concurrent model isolation; history/trace identity; replay conflicts; recovery without a key after default changes; fixed-model retry; invalid choices; evidence-only legacy migration |
| [test_openai_reviewer.py](../tests/test_openai_reviewer.py) | Structured request schema, numbered/untrusted source, request controls; refusal/incomplete/missing parsed output treated as failure |
| [test_findings.py](../tests/test_findings.py) | Resolution persistence and reopening; code, other findings, and other runs unchanged; invalid updates and missing IDs |
| [test_review_history.py](../tests/test_review_history.py) | Snippet-scoped ordering and preservation of previous resolutions |
| [test_discussions.py](../tests/test_discussions.py) | Follow-up history; persistence and rerun/finding isolation; submission replay/conflicts; failures/timeouts; guarded retries and stale completion; shutdown/startup recovery; recent-ten successful context window; missing configuration; shared concurrency and queue timeout |
| [test_conversations.py](../tests/test_conversations.py) | Same-finding conversation isolation; restart persistence; keyless/idempotent creation; ownership; conversation-scoped replay/retry; active-finding guards; migration preserving original messages |
| [test_openai_discussion.py](../tests/test_openai_discussion.py) | Context and role ordering; plaintext and request controls; refusal/incomplete/empty replies; safe messages for provider failures |
| [test_quality.py](../tests/test_quality.py) | Annotation round trips, revisions, restart/export; stale-write rejection; completion requirements; source hashes/frozen snapshots; invalid case/run/finding identities; failed/empty outputs; choices-only completion; compatible reasons; no model calls |
| [test_eval_grading.py](../tests/test_eval_grading.py) | Category/range/cue matching; duplicate findings; separate severity grading; failed positive/negative attempts retained in aggregates; valid fixture IDs/ranges |
| [test_tracing.py](../tests/test_tracing.py) | Metadata-only spans; concurrent context isolation; failure/cancellation/interruption; best-effort trace storage; API job/provider-adapter correlation using mocked SDK responses |

## Browser coverage

Product scenarios in [workflow.spec.ts](../tests/browser/workflow.spec.ts):

1. Create, review, highlight source, resolve, converse, rerun, and restore historical resolutions/conversations after reload.
2. Retry review/reply failures; preserve an unsent question when closing/reopening; avoid duplicating a retried question.
3. Drop a persisted discussion response, reload, and recover one saved turn; render returned HTML-like content as text.
4. Display zero findings and filter the dashboard.
5. Protect drafts when choosing examples; check discussion width and keyboard focus restoration.
6. Create independent conversations on one finding; retain separate context, messages, drafts, selection, and resolutions across switching/reload.
7. Drop a new-conversation response and recover the same conversation after reload.
8. Drop a persisted review response, let the run complete, and recover without reload: one run and one mock provider call; deliberate rerun creates a new request and second call.
9. Repeat the review-recovery scenario after reload. Both recovery tests also change the browser preference while a request is uncertain and verify its original model remains fixed.
10. Select GPT-5.6 Sol for a review and GPT-5.5 for a reply; remember selection across reloads; preserve review/reply model labels; keep a failed reply's original model on retry while later questions use the new choice; inspect desktop/narrow layouts.
11. Recover a legacy plain-UUID pending review without changing its recorded model or creating a second call.

Annotation scenarios in [quality.spec.ts](../tests/browser/quality.spec.ts):

12. Complete/export with choices only and empty prose; retain drafts, saved revisions, completion and history; restore partial API-written drafts.
13. Reject a stale second-tab save without losing its unsaved evidence or overwriting the newer saved judgment.
14. Advance saved first-step drafts through visible continuation actions; focus missing-answer guidance; avoid prematurely completing the case.
15. Delay a successful save response, leave/return and edit again, then deliver the old response: newer evidence survives navigation/reload. Reverting edits to the baseline also clears the obsolete browser draft.

The model-selection suites use mocked providers/SDKs, including the adapter-to-trace checks; no new paid model calls were made. The existing local database was backed up before migration 007. Model choices are not a claim that every account can access every model, or that their review quality has been measured.

## Manual and live verification

The developer has confirmed these manual E2E groups: snippet management, review/display, finding resolution/history, multi-turn and independent conversations, offline mutation failure/recovery, and persistence after API restart. The latest restart changed the API worker process and retained the saved snippet/review/finding/conversation/annotation records; the developer confirmed their browser view afterward.

The final manual annotation/export walkthrough was deferred for the demo. Its automated tests passed, but it is not recorded as manually accepted. No human judgments were created on the developer's behalf.

Earlier live checks verified an OpenAI review and two follow-up replies on a synthetic averaging example. The quality work ran 50 calls across three prompts and ten development cases. See [quality evidence and limitations](quality.md). These historical calls are distinct from the mocked software tests.

## Limits and historical evidence

- Chromium desktop/narrow viewports do not establish Safari, Firefox, or real-device compatibility. Focus/width checks are not a complete accessibility audit.
- Tests establish software behavior, not semantic model accuracy, universal prompt-injection resistance, or correctness of generated fixes.
- Restart tests cover application recovery and saved data; they do not establish durability under arbitrary OS kills, hardware faults, or prolonged storage outages.
- There is no multi-worker/load test, tool-execution safety evaluation, distributed trace backend, or production deployment verification.
- The original fresh-clone verification at `6aa8794` installed from lockfiles and checked production startup/restart on macOS arm64 (Node 25.6.1, npm 11.9.0, uv 0.11.7, Python 3.12.13). It covered the then-current 56-test version; it was not repeated as a fresh install for every later commit or on all minimum supported versions.
- Later milestones added evaluations/tracing (63 backend tests), annotation (69 then 72), independent conversations (77 and 20 browser cases), the three review repairs (82 and 26), model selection (88 and 30), and GPT-5.5/GPT-5.6 Sol compatibility (90 and 30). Git history retains the detailed development records. The current suite emits one upstream Starlette/httpx deprecation warning.

## Short demo

Configure the key and start the app before presenting. New reviews/replies make billable calls; saved results can be shown without another call.

1. Create or open **Average calculation**:

   ```python
   def average(values):
       return sum(values) / len(values)
   ```

2. Run a review; show progress and structured findings. Empty-list division is a useful example, but exact wording/severity is model-dependent.
3. Select a finding's line reference, accept it, then reopen it. Explain that acceptance records a decision without modifying source.
4. Ask a question and a follow-up. Create a new conversation, switch back, and refresh to show separate persisted histories.
5. Show dashboard filters and review history. Briefly show `npm run trace:calls -- --limit 5` and the saved quality report. Human annotation is an optional extension to the demo.

The repository includes source, migrations, lockfiles, tests, setup/design documentation, and [five AI-use examples](../AI_USAGE.md). Local secrets, databases, dependencies, and test/build artifacts are excluded. Preserve Git history when submitting. External publication/submission has not been performed.
