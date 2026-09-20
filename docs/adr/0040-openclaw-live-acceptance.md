# ADR 0040: Separate OpenClaw contract CI from explicit live acceptance

- Status: Accepted
- Date: 2026-09-04

## Context

The OpenClaw executor depends on an external Gateway, paired device identity, provider credentials,
and a compatible official wire protocol. Unit tests alone do not prove that a deployed Gateway can
preserve idempotency and session continuation. Conversely, contacting a live agent from ordinary CI
would require secrets, incur provider usage, and make the quality gate depend on external state.

## Decision

Use two complementary verification layers:

- CI installs the exactly pinned official OpenClaw client and protocol packages on their minimum
  supported Node.js version and executes the isolated bridge contract tests.
- The optional executor package provides `jb-openclaw doctor` for non-turning prerequisite and
  Gateway inspection.
- `jb-openclaw acceptance` is an explicit operator action against one configured deployment. It
  proves stable-run replay for one idempotency key and same-session continuation with a new key.
- Cancellation is a separate opt-in probe because it starts an additional provider turn.
- Diagnostics reject URL-embedded credentials and remote TLS without a pinned fingerprint. Reports
  contain only safe connection metadata, aggregate counts, statuses, and run identifiers.

Live acceptance uses a dedicated session key and operator-selected idempotency prefix. It is not run
automatically during package installation, worker startup, or CI.

## Consequences

- Pull requests detect official protocol and bridge regressions without needing Gateway secrets.
- Operators retain a repeatable final check for each real deployment and credential boundary.
- Live acceptance may consume provider quota, so it remains deliberate and documented.
- Passing CI establishes protocol compatibility, not end-to-end production readiness; a target
  deployment must also pass the explicit acceptance flow before release.
