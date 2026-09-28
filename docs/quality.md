# Review quality, evaluations, and tracing

## What we measure

Application tests answer whether review/discussion requests are valid, isolated, persisted, retryable, and correctly rendered. They cannot establish whether the model found the right issue. This project now has three complementary checks:

1. **Deterministic software tests:** schema, line bounds, state transitions, persistence, context isolation, retries, trace metadata and privacy, grading behavior; plus desktop/narrow browser workflows with a fake provider. No API calls.
2. **Live quality regression:** ten authored synthetic cases in `evals/cases.json`, six with an expected issue and four expected to be quiet. Cases include ordinary bugs, SQL injection, async iteration, guarded code, parameterized SQL, and prompt-like comments. Labels are authored expectations, not externally validated ground truth. In particular, handling empty inputs is a chosen review convention, not proof of every caller's requirements.
3. **Semantic review:** inspect each returned finding and suggested fix against its source and rubric below. Automated candidate matching is only a triage aid. There is no LLM judge or independent human-labeled benchmark in this MVP.

This approach follows the [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices): use task-specific cases and combine metrics with judgment. It runs locally through the existing Responses client, without a hosted eval service or additional account.

## Running evaluations

From the project root with the server-side key configured:

```sh
# No calls unless --live is explicitly supplied. Ten calls by default.
npm run eval:review -- --live
# Repeat the fixed cases to observe variability (20 calls).
npm run eval:review -- --live --repeats 2
# Target a case, or compare a saved prompt; use a NEW output directory.
npm run eval:review -- --live --case safe-sql --prompt evals/review-v1.txt --output work/evals/my-baseline
```

Calls are serial, with the configured timeout and no SDK retries. Each run writes a new `work/evals/<timestamp>/` directory containing the exact prompt, dataset snapshot, JSON results, and a separate trace database. JSON is checkpointed after every attempt. Provider failures are counted and cause a nonzero exit; low quality scores are reported for review, not hidden or silently retried. Outputs contain the synthetic fixture responses; do not substitute sensitive production code into shareable reports.

Results include configured model, prompt version/hash, dataset hash, base Git revision/dirty flag, SDK version, per-case output, repeat number, latency, and available token usage. A model alias can change at the provider; this metadata improves reproducibility but cannot make stochastic outputs identical.

The deterministic grader requires category agreement, source-range overlap, and an issue-specific cue. Each finding can match at most one expected issue. Remaining findings are candidates for false positives or duplicates; unmatched expected issues are candidates for misses. Broad line ranges may pass overlap even when imprecise, and keyword matches may be semantically wrong. Severity agreement is measured separately. Negative cases pass only with a successful empty response; failed calls do not count as correct silence. Failed positive attempts remain in the recall denominator. Precision is null when no findings were returned.

## Observed results — September 28, 2026

Same model (`gpt-4.1-mini`) and fixed dataset throughout. These are development-set measurements, with unequal baseline/candidate repeat counts. They are not a held-out estimate, statistical significance claim, or production accuracy percentage.

| Measurement | Baseline v1 (1 pass) | Selected v2 (2 passes) | Experiment v3 (2 passes) |
| --- | --- | --- | --- |
| Successful calls | 10/10 | 20/20 | 20/20 |
| Expected issues matched | 6/6 | 12/12 | 12/12 |
| Matched / returned findings | 6/8 | 12/14 | 12/14 |
| Severity matches among matched findings | 3/6 | 12/12 | 12/12 |
| Quiet negative cases | 2/4 | 6/8 | 6/8 |
| Median latency | 1,419 ms | 1,293 ms | 1,301 ms |
| Input / output tokens | 5,164 / 791 | 12,988 / 1,479 | 14,428 / 1,403 |

Raw, synthetic results are committed in `evals/reports/`; prompt snapshots are `evals/review-v1.txt`, `review-v2.txt`, and `review-v3.txt`. Across all 50 calls, reported usage was 32,580 input and 3,673 output tokens. No currency estimate is hardcoded because pricing can change.

**Decision:** select v2. It calibrated ordinary exceptions and off-by-one defects to warning, while retaining critical for SQL injection. It also stopped flagging the injection-like comment in these trials. V3 used more prompt tokens and did not improve these scores.

**Known remaining failure:** parameterized SQL still received speculative style suggestions in both candidate passes. The returned `fetchall()` to `fetchone()` change would alter result cardinality without a stated requirement. V3 also suggested imaginary column names. These are recorded as unwanted findings; no post-processing rule hides SQL/style outputs to improve the score.

Codex inspected the candidate descriptions and suggestions, not just the metric totals. Suggestions to choose arbitrary defaults for empty averages still require the user's API contract; mutable-default code snippets are explanatory fragments, not automatically validated patches. SQL impact wording can overstate what an unspecified driver permits, even when injection itself is real. No generated fixes were executed or certified. An independent human should review this rubric and labels before treating scores as authoritative.

## Manual grading rubric

For each case, first inspect the code without reading the proposed reference or model output. Record your observations and explicit/unknown input assumptions, then reveal and validate the reference, and finally assess the model outputs. Use the local Human review workspace below to persist judgments and evidence.

| Dimension | Questions |
| --- | --- |
| Correctness | Can you construct an input or trace showing the described behavior? Does it depend on an unstated API/schema/scale assumption? |
| Coverage | Which expected issues were found or missed? Does an unexpected finding reveal a real missing label? Update labels transparently, never merely to raise a score. |
| Precision / duplication | Is each finding independently actionable? Does it repeat another finding or express only a style preference? |
| Localization | Are the lines valid and as narrow as practical? Overlap alone is insufficient. |
| Severity | Is the impact supported? Ordinary localized bugs are warning; reserve critical for supported exploitation, data loss or broad failure. |
| Fix usefulness | Does the suggestion solve the issue without inventing schema, changing intended behavior, or introducing another bug? A textual suggestion is not an applied/tested patch. |
| Stability | Do repeated runs preserve the same substantive decisions? Investigate disagreement instead of selecting the best run. |

Next quality work should add independently labeled, representative/held-out cases and pairwise human comparisons. Expand languages, correct code, ambiguous contracts, multiple interacting issues, and longer snippets before drawing broader conclusions. Accept/dismiss is a workflow decision; it is not automatically ground truth.

## Human annotation workspace

Open `http://127.0.0.1:5173/#/quality` (or `/#/quality` on the production server). The header's **Human review** link also opens it. No API key or provider call is needed to annotate existing results.

1. Choose **candidate-v2**, enter your reviewer name, and select **Start / resume review**. The same name and source resume the same session. Different names create separate assessments; this is a local name label, not authentication.
2. Pick a case in the sidebar. Start with `off-by-one` if you want a small, concrete example. Inspect the source and record **Your observations and evidence** and **Input / behavior assumptions**. A minimal input/result or execution trace is useful. Do not run arbitrary generated fixes automatically.
3. **Reveal proposed reference**. Choose **Approved**, **Needs changes**, or **Uncertain**, and explain why. For **Needs changes**, write the corrected issues, line ranges, impact and valid fix direction in **Proposed reference changes** (or explicitly propose no issues). Approval means supported by the context the model actually saw. Unknown empty-input behavior is a valid reason for uncertainty. References and their private notes were not sent to the model.
4. **Reveal model outputs**. For each run, mark every finding **Correct**, **Incorrect**, **Uncertain**, or **Duplicate**, then rate line location, severity, and fix usefulness. Add evidence and explain rating problems. Use **Not applicable** for a missing fix. Assess **Coverage** even when no findings were returned; record missed issues and affected lines, explain correct silence, or mark uncertainty. A valid extra finding can expose an incomplete reference. A failed call is always a failed assessment of coverage, never a clean review.
5. Use **Save draft** whenever pausing, or **Complete & next case** after every dimension and reason is filled. The v2 report contains 10 cases and 20 outputs (two runs per case). Runs must be assessed separately. Completion means the assessment is filled, not that the reference is approved; uncertainty is allowed.
6. **Export saved annotations** downloads JSON containing original dataset/report snapshots, hashes and report metadata, your latest labels, reviewer name, and every saved revision. Keep or share this file for adjudication. The export excludes unsaved browser drafts. **Download this draft** can rescue one unsaved case before resolving a conflict.

Saved sessions and append-only annotation revisions live in the app's local SQLite database (`data/reviewer.db`, ignored by Git). Reloading or restarting preserves saved work. When browser storage is available, unsaved drafts survive switching cases and reloading in the same tab; they are not a durable substitute for **Save draft** and may disappear when that tab closes. Unavailable browser storage displays a warning. Conflicting writes return 409 without overwriting the newer annotation. Download/copy your draft before choosing **Load saved version**.

Sources include the committed v1/v2/v3 reports and `work/evals/*/results.json` with matching adjacent `dataset.json` snapshots. Committed reports require the current `evals/cases.json` bytes to match their dataset hash; mismatches are listed as unavailable rather than silently assigning old outputs to new code. Creating a session freezes the source and labels; existing sessions remain readable if the files later change or disappear. No automatic call, source/finding modification, reference promotion, or gold-accuracy calculation happens here. Proposed reference changes remain human notes until deliberately adjudicated and versioned. If a correction changes the code or input contract visible to the model, rerun the revised case instead of grading the old output against hidden requirements.

This workspace supports a single reviewer's judgments per named session, not consensus adjudication or a held-out benchmark. After checking these development cases, create independent held-out cases before making an accuracy claim. Existing automatic heuristic scores are unchanged by annotations.

## Local model-call tracing

Migration `003_model_calls.sql` stores a span for each scoped real-provider attempt. Review spans use the review-run ID; discussion spans use the turn ID and retry attempt; evaluation spans use a separate case/attempt ID. A shared context variable isolates concurrent calls.

Recorded fields: operation, subject/attempt, configured model, prompt version, start/finish, provider-call duration, succeeded/failed/cancelled/interrupted status, input/output tokens when available, provider request/response IDs when available, and exception class. Prompt text, source, user messages, assistant replies, key values, and exception bodies are **not** duplicated into trace rows. The application's own snippet/discussion tables still store their normal content.

```sh
npm run trace:calls -- --limit 20
npm run trace:calls -- --subject REVIEW_OR_TURN_UUID
npm run trace:calls -- --database work/evals/candidate-v2/calls.db --limit 5
```

The call duration excludes time waiting for the shared concurrency slot; job timestamps capture queue/lifecycle timing. A timeout during a provider call produces a cancelled span and a failed/timed-out job. A queued timeout makes no provider span. Startup marks unfinished spans interrupted. Failed SDK calls may have no token/request metadata; null means unavailable, not zero. Known failures have safe user-facing explanations on the corresponding review/turn record; the span retains an error class only. Trace writes are best effort and log only exception class if storage fails.

There is no distributed tracing backend, automatic cost calculator, production dashboard, or automatic trace export. Local SQLite metadata is enough to inspect this single-process MVP without an observability service. Separately, Playwright retains a browser action/network trace and screenshot on failed tests under ignored `test-results/`; those are debugging artifacts, not model-call traces.
