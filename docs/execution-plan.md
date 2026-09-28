# MVP execution plan

Original target: 7 hours of planned work plus 1 hour buffer, before the AI conversation scope was clarified. Discussion is now included as an additional milestone before final verification; the original estimate is not a promise that the expanded scope fits the same time budget.

1. **Foundation (completed):** React/API startup, file database and migrations, shared contracts, environment example, README and AI log, initial meaningful commit.
2. **Snippets (completed):** create/list/detail, metadata and filters, syntax highlighting and line numbers. Prove persistence across restart.
3. **Review integration (completed):** create a review, invoke a real LLM, validate complete output, transactionally save findings and success/failure.
4. **Review lifecycle (completed):** polling, clear loading/errors, manual retry, duplicate-trigger protection at the API boundary, interrupted-run recovery.
5. **Finding interaction (completed):** code alongside findings, line navigation, severity/category/description/fix, persistent accept/dismiss.
6. **Per-finding AI conversation (completed):** add discussion-turn persistence and request deduplication; history/send/retry endpoints; contextual OpenAI replies; expandable Discuss UI with pending/failure states and saved history. Keep finding resolution independent. Follow the [conversation design](data-contract.md#per-finding-ai-conversation) for context boundaries, retry semantics, and acceptance criteria.
7. **Verification (completed):** end-to-end snippet/review/finding/discussion workflow, zero findings, malformed output, provider failure, isolation, retry, and persistence. Reproduce setup and build in a clean checkout.
8. **Delivery preparation (completed):** clean setup instructions, final architecture/tradeoffs, future work, honest AI usage examples, inspect commit history.

Keep commits tied to completed increments. Record AI examples while developing. The assignment author prefers follow-up conversation with the AI and accepts recording finding acceptance without applying a fix; these choices are now part of the design. Authentication, snippet editing/deletion, automatic fixes, PR import, streaming, rich chat rendering remain outside the MVP.

Final verification and a short demo are recorded in [verification.md](verification.md). All implementation and local delivery-preparation milestones are complete. External publication/submission is a separate user action.

## User-approved improvements after the initial MVP

9. **Reading and demo experience (completed):** wider discussion workspace, persisted drafts on close, keyboard focus restoration, responsive layout, safe sample-code entry points.
10. **Review history (completed):** scoped list API and URL-persisted selector, preserving earlier findings, resolutions and conversations.
11. **Quality evaluation and local tracing (completed):** versioned fixed fixtures/prompts, opt-in live runner, transparent candidate grading, saved results and rubric, safe model-call metadata.
12. **Repeatable browser regression (completed):** five real-API workflows at desktop and narrow widths, isolated SQLite and deterministic providers, failure screenshots/action traces.

These improvements were explicitly requested after the original MVP. They are additional scope, not a claim that the original time estimate included all of this work.
