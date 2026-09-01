# ADR 0002: Persist a guarded run state machine

- Status: Accepted
- Date: 2026-09-01

## Context

Runs will be resumed by workers, observed by multiple clients, and recovered after process
failures. A status value without transition rules would allow impossible histories and make
recovery behavior ambiguous.

## Decision

Define run transitions in the domain layer and persist every run with a durable status,
timestamps, attempt number, and optimistic concurrency version. PostgreSQL constraints protect
enumerated values and uniqueness. The current state machine allows a bounded repair loop from
verification back to running.

## Consequences

- API and workers must use the same transition methods.
- Terminal runs cannot be reopened; a retry creates a new attempt.
- The database schema can reject unknown states while orchestration rules remain testable without
  a database.

