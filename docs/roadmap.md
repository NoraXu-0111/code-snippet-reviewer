# Prioritized extensions

These are proposed next steps, not implemented features. Keep the local MVP small until a concrete workflow needs more infrastructure.

## 1. Improve review-quality evidence

Build an independently reviewed held-out dataset spanning correct code, ambiguous contracts, multiple issues, longer snippets, and more languages. Adjudicate conflicting annotations and version the references. Measure false positives, misses, localization, severity, and fix usefulness separately; retain failed calls in results. Existing fixtures, prompt snapshots, raw reports, grading functions, and annotation revisions provide the starting point. Completion: compare a candidate against the baseline on untouched cases, with human-reviewed disagreements.

## 2. Extend observability before adding agent steps

Retain `trace_subject`, the provider decorators, model/prompt metadata, and domain IDs. Add workflow trace IDs, span IDs, parent span IDs, and structured lifecycle events for orchestration, model calls, retrieval, and tools. Propagate context explicitly across queued jobs/processes; the current ContextVars only establish local task context. Add correlated JSON logs and central redaction, including the generic exception handler, before exporting logs. Track queue time separately from execution time and aggregate available usage per workflow.

Completion: one workflow can be followed from its HTTP request through each step/retry using the same trace ID, with tests for parallel context isolation, failures, and sensitive-data exclusion. An external trace sink can be added behind a small recorder interface when needed; no particular framework is required by the current design.

## 3. Make longer workflows durable and bounded

Reuse validated contracts, provider protocols, replay keys, and guarded state transitions. Add explicit workflow/step records, persisted dependencies/checkpoints, and resumable execution. Move scheduling out of the web process into a durable worker with ownership leases, bounded queues, cancellation, and per-step idempotency. A trace is diagnostic evidence, not a workflow checkpoint or source of execution truth.

Set workflow token/time/call budgets and a token-aware context policy. If tools are introduced, allowlist them, validate inputs/outputs, isolate code execution, and require approval for consequential writes. Provider retries and tool side effects need their own recovery policies; request deduplication alone does not make them exactly-once.

Completion: crash between two steps, resume without repeating committed side effects, preserve the trace, and stop at the configured budget. Add deterministic tool/provider fixtures to the existing failure/replay test approach.

## 4. Expand deployment and editing only with their prerequisites

Before shared hosting, add authentication, per-user data ownership/authorization, retention controls, and workload limits. Reassess SQLite versus a server database based on measured concurrency; a database switch alone does not provide durable scheduling.

Before editing snippets or applying suggested patches, introduce immutable snippet revisions and bind reviews to an exact revision. Show a patch preview and validate it in an isolated environment. Streaming, richer chat rendering, PR import, pagination, and additional browser support can follow demonstrated user needs.

## Existing foundation versus missing pieces

| Reusable now | Required for a richer agent workflow |
| --- | --- |
| Review/Discussion provider protocols | Tool and orchestration interfaces |
| Pydantic schemas and server-owned context | Typed step inputs/outputs and explicit dependencies |
| Persisted jobs, submission replay, attempt guards | Durable checkpoints, leases, step-level side-effect recovery |
| Flat model-call spans and task-local context | Parent/child traces and cross-process propagation |
| Mock providers, browser regressions, eval snapshots | Multi-step/tool fixtures and workflow-level quality evaluation |

The current app has asynchronous LLM-backed jobs and conversations. It does not yet implement an autonomous tool-using agent loop.
