---
name: safe-implementation
description: Implement a bounded change while preserving unrelated work and producing verification evidence.
---

# Safe implementation

Use the supplied plan and any repair guidance as inputs.

1. Inspect the current repository state before editing.
2. Preserve unrelated user changes and existing architectural boundaries.
3. Make the smallest cohesive change that satisfies the request.
4. Add or update tests for changed behavior.
5. Run proportionate checks and report exact results.
6. Return only the structured result required by the active phase contract.

Never claim a check passed when it was not executed.
