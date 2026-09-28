# MVP execution plan

Target: 7 hours of planned work plus 1 hour buffer. This is a planning estimate, not a claim about time already spent.

1. **Foundation (completed):** React/API startup, file database and migrations, shared contracts, environment example, README and AI log, initial meaningful commit.
2. **Snippets (completed):** create/list/detail, metadata and filters, syntax highlighting and line numbers. Prove persistence across restart.
3. **Review integration:** create a review, invoke a real LLM, validate complete output, transactionally save findings and success/failure.
4. **Review lifecycle:** polling, clear loading/errors, manual retry, duplicate-trigger protection at the API boundary, interrupted-run recovery.
5. **Finding interaction:** code alongside findings, line navigation, severity/category/description/fix, persistent accept/dismiss.
6. **Verification:** end-to-end user workflow, zero findings, malformed output, provider failure, review isolation and persistence.
7. **Delivery:** clean setup check, architecture/tradeoffs, future work, honest AI usage examples, inspect commit history.

Keep commits tied to completed increments. Record AI examples while developing. Discussion awaits the assignment author's clarification. Authentication, snippet editing/deletion, automatic fixes, PR import, streaming, and review-history navigation are outside the initial scope.
