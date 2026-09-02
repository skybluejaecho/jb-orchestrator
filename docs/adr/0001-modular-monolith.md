# ADR 0001: Start as a modular monolith

- Status: Accepted
- Date: 2026-09-01

## Context

The orchestrator needs an API, durable workflows, workers, agent adapters, skills, artifacts,
and multiple clients. Splitting these concerns into deployable services before their boundaries
are proven would add operational and consistency costs.

## Decision

Build a single Python distribution with explicit domain, application, infrastructure, and
interface boundaries. Run the API and worker as separate processes from the same codebase.
Use PostgreSQL as the source of truth. Add MCP and GUI integrations as adapters.

## Consequences

- Transactions and local development remain simple during the first releases.
- Module boundaries are enforced in code and tests rather than by network calls.
- A module may be extracted later when scale, ownership, or isolation requirements justify it.

