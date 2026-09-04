# ADR 0039: Allow additive request-scoped Skills on task nodes

- Status: Accepted
- Date: 2026-09-04

## Context

Versioned Workflows and Phase Packs provide reproducible defaults, but users also need to combine
registered internal or third-party Skills for one request without publishing a new Workflow version.
Unrestricted overrides could silently remove required context or make retries produce different
executions.

## Decision

Allow a dispatch to carry zero or more node Skill add-ons. Every add-on names one task node and one
or more exact `key@version` Skill references. The Control Plane applies them with these rules:

- node keys are unique and must identify task nodes in the selected Workflow;
- Skill references are normalized, deduplicated, and resolved from the immutable catalog;
- add-ons are unioned with direct node Skills and never remove existing or Phase Pack Skills;
- the normalized add-ons are part of the idempotency payload digest and durable request event; and
- the augmented nodes and complete resolved Skill metadata are copied into the execution Snapshot.

The project-scoped Workflow options response includes safe summaries of the latest registered
Skills so scoped Control Agents and Jarvis can offer choices without exposing source URIs, digests,
or Skill contents. Materialization and digest verification remain Worker responsibilities.

## Consequences

- Planning, implementation, verification, or custom task nodes can receive request-specific context.
- Existing Workflow versions remain immutable and retain their required behavior.
- A retry cannot change Skill choices under the same idempotency key.
- Non-task nodes cannot receive executable context packages.
- Removing or replacing required Skills still requires publishing a new Phase Pack or Workflow.
