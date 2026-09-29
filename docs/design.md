# Design

## Goal and scope

Help a developer submit an immutable code snippet, inspect structured AI findings, record decisions, and ask follow-up questions. The assignment author clarified that follow-up conversation is preferred and acceptance may simply record a decision. This implementation supports both choices. It is a local, single-process application; source code is never executed and suggested fixes are not automatically applied.

## Architecture

```text
React + TypeScript -> FastAPI + Pydantic -> SQLite
                              |
                     asynchronous job services
                              |
                     provider adapters -> OpenAI
```

React owns interaction and polling. FastAPI owns validation and context selection. Pydantic generates the OpenAPI schema and TypeScript contracts. SQLite avoids an external database service and provides transactions, foreign keys, and partial unique indexes. Checksummed migrations are append-only. Hash routes preserve frontend URLs without server-side route fallback.

A server-owned OpenAI catalog supplies the default and selectable models. Browser preference affects only new requests; each persisted job fixes its own model. Adapters receive separate settings per model, and traces record that same selection. Older model identities are recovered only from trace evidence. GPT-5.5 and GPT-5.6 Sol use explicit `reasoning.effort=none` to preserve a non-reasoning latency baseline; quality improvements are not assumed.

Provider adapters implement small `Reviewer` and `DiscussionProvider` protocols. Job services own persistence, timeouts, and retries; adapters own model requests and response interpretation. Tests can replace a provider while exercising the actual API and database.

## State and ownership

```text
Snippet -> ReviewRun -> Finding -> DiscussionConversation -> DiscussionTurn
```

- A **Snippet** stores title, language, original code, and creation time. Immutability keeps historical line references meaningful.
- A **ReviewRun** tracks queued/running/succeeded/failed execution. A new review produces new findings; earlier results remain accessible.
- A **Finding** stores line range, severity, category, description, optional fix, and open/accepted/dismissed resolution. Acceptance never changes code or review completion. Dashboard status reflects the latest review even if findings remain open.
- A **Conversation** scopes history within one finding. New conversations start without earlier exchanges while retaining snippet/finding context.
- A **Turn** pairs one question with a reply and execution attempt. Retrying a failed reply retains the question and increments its attempt.

Human evaluation sessions/revisions are separate from product findings. Completing an annotation or accepting a finding does not establish correctness ground truth.

## Execution and recovery

Persist a queued job before scheduling it. Review and discussion tasks share two provider slots; SQLite permits one active review per snippet and one active reply per finding. The configured timeout covers queue wait and execution. The frontend polls active work every two seconds.

Each review submission has a persistent client UUID, unique per snippet. Replaying it returns the existing run even after completion or restart. New reviews require new UUIDs. Questions and conversation creation have equivalent replay protection; discussion completion also checks the attempt number. Browser recovery survives same-tab reload while storage is retained. None of these guarantees exactly-once remote execution.

Validate complete model output and line bounds before committing findings and successful review status together. Read status/findings within one database snapshot. Failed or partial output is an explicit failure, distinct from a valid empty result. Shutdown/startup marks unfinished jobs failed; jobs are not automatically resumed. One process owns each database.

## Model context and boundaries

Reviews receive language and numbered source. Replies additionally receive the selected finding and up to ten recent successful exchanges from that conversation. Context is loaded through server-owned relationships; clients cannot supply replacement source or system instructions. Failed turns remain visible but do not enter model context.

Adapters request structured review output, disable SDK retries, and use `store=False`; that option is not a zero-retention guarantee. Credentials stay server-side. Code, findings, and replies render as escaped/plain text. Prompt instructions supplement these boundaries; they do not establish complete prompt-injection resistance.

## Observability and quality

`trace_subject` and the provider decorator record local model-call metadata correlated with review/turn IDs and attempts. Console logging covers requests and failures. These are useful extension points, but current spans are flat and console logs lack uniform correlation and redaction. See [observability details](quality.md#local-model-call-tracing).

Deterministic API/database/browser tests validate behavior and recovery. Separate synthetic evaluations and human annotations assess model quality; the development dataset is not a held-out benchmark. See [test coverage](verification.md) and the [quality methodology](quality.md).

## Tradeoffs and next steps

SQLite plus in-process tasks keeps local setup small but does not provide durable scheduling or multi-worker ownership. Full snippets and a ten-exchange window are simple context rules, not a token-budget strategy. Finding resolutions use last-write-wins; evaluation annotations use revision conflict checks. Tracing is best effort and cannot serve as workflow state.

The [prioritized roadmap](roadmap.md) explains how to build on these boundaries for agent workflows. Detailed limits, states, and endpoints are in the [data contract](data-contract.md).
