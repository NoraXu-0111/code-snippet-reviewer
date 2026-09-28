# AI usage log

Tool: Codex. This is an ongoing development record, not a final claim that the assignment is complete.

## Example 1 — Requirements and ambiguous scope

Codex extracted the assignment and distinguished explicit requirements from examples and preferences. It identified that discussion appears in the overview but is absent from the detailed interaction requirements. The developer sent a clarification to the assignment author, who replied that follow-up AI conversation is preferred and either accept behavior is acceptable. The developer agreed to add per-finding AI conversation; the design and execution plan now include it as a pending implementation milestone. Acceptance continues to record resolution without applying code changes.

## Example 2 — Review versus finding state

Codex proposed separate Snippet, ReviewRun, and Finding models. The developer explicitly agreed to separate review execution state from finding resolution. The foundation implements separate tables and a database-level uniqueness constraint for active reviews. This avoids conflating “analysis finished” with “findings accepted.” The finding interaction step tests that changing a resolution leaves code, review status, and other findings unchanged. Browser verification included a stopped test server to confirm that a failed update does not falsely display an accepted state.

## Example 3 — Structured review output and failure validation

Codex implemented Responses API structured output backed by Pydantic, then checked line bounds separately: schema-valid output can still refer to a nonexistent source line. Tests cover refusal/incomplete output, timeouts, reruns, restart recovery, and rollback after a simulated failure on the second finding insert. Two small live checks used a synthetic averaging function; the browser review correctly identified a line-2 division-by-zero case. Its critical severity label is arguably too strong for an unspecified input contract, so successful schema/integration checks are not treated as proof of review quality. Broader severity calibration remains future work.

## Example 4 — Developer choice overrides the default backend

Codex initially chose a TypeScript backend because the stack was undecided. The developer requested Python before the first commit. Codex replaced Fastify with FastAPI, moved domain validation to Pydantic and tests to pytest, and retained the SQLite schema and React frontend. The initial default caused avoidable rework; the developer's language preference is more important than sharing one language across the stack.

## Example 5 — Latest-review filtering and cross-language contracts

Codex implemented SQL that selects each snippet's latest review before filtering by status, and added a regression test where an old success is followed by a failure at the same timestamp. Frontend types are generated from FastAPI OpenAPI rather than independently maintained. The generator rejected the initial TypeScript 7 dependency; Codex switched to the generator's supported TypeScript 5 instead of bypassing the peer-dependency check. This compatibility issue took extra work and illustrates why generated scaffolds still need integration checks.

## Overall assessment — provisional

AI helped translate requirements into a concrete schema and connected scaffold quickly. The unconfirmed backend default caused rework. Generated configuration and model output still required review: dependency compatibility and severity calibration are examples. No measured time saving is claimed. Add the developer's own assessment before final submission.
