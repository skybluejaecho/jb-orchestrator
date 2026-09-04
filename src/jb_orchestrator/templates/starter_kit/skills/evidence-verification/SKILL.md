---
name: evidence-verification
description: Evaluate an implementation using reproducible evidence rather than agent memory.
---

# Evidence verification

Treat the implementation artifact as a claim that must be independently checked.

1. Compare the result with the original request and acceptance criteria.
2. Inspect changed contracts, tests, and failure paths.
3. Separate confirmed defects from residual risks or unverified assumptions.
4. Include reproducible commands or observations for every conclusion.
5. Return only the structured result required by the active phase contract.

Do not approve work solely because the implementation agent reported success.
