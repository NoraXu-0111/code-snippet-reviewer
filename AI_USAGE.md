# AI usage log

Tool: Codex. This is an ongoing development record, not a final claim that the assignment is complete.

## Example 1 — Requirements and ambiguous scope

Codex extracted the assignment and distinguished explicit requirements from examples and preferences. It identified that discussion appears in the overview but is absent from the detailed interaction requirements. The developer sent a clarification to the assignment author. Discussion implementation remains pending that answer.

## Example 2 — Review versus finding state

Codex proposed separate Snippet, ReviewRun, and Finding models. The developer explicitly agreed to separate review execution state from finding resolution. The foundation implements separate tables and a database-level uniqueness constraint for active reviews. This avoids conflating “analysis finished” with “findings accepted.”

## Example 3 — Generated foundation and verification

Codex generated the initial TypeScript/React/Fastify scaffold, SQLite migration, shared Zod contracts, and targeted tests. The initial draft used a fixed development proxy port even though the API port was configurable; Codex revised the Vite configuration to read the configured port. This is an agent self-correction, not a claimed human override.

## Example 4 — Developer choice overrides the default backend

Codex initially chose a TypeScript backend because the stack was undecided. The developer requested Python before the first commit. Codex replaced Fastify with FastAPI, moved domain validation to Pydantic and tests to pytest, and retained the SQLite schema and React frontend. The initial default caused avoidable rework; the developer's language preference is more important than sharing one language across the stack.

## Overall assessment — provisional

AI helped translate requirements into a concrete schema and connected scaffold quickly. The unconfirmed backend default caused rework. Generated configuration still required review for cross-file consistency, as the port mismatch illustrates. No measured time saving is claimed. Add observed LLM-integration and UI examples, and the developer's own assessment, before final submission.
