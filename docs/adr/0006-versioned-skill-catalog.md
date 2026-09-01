# ADR 0006: Keep skills as versioned context packages

- Status: Accepted
- Date: 2026-09-01

## Context

Users need to combine internally authored and third-party skills for individual workflow steps.
Skills must remain distinct from executor runtimes and MCP servers, and an in-flight workflow must
not change when a catalog entry receives a newer version.

## Decision

Treat a skill as a reusable context package identified by `key@version`. Store its description,
source kind and URI, entrypoint, SHA-256 content digest, and optional metadata in an immutable
catalog entry. Workflow nodes reference one or more exact versions. Starting a workflow resolves
those references and copies the complete catalog metadata into the execution snapshot.

The database does not copy arbitrary skill files. A later installer/materializer will fetch or
locate the source and verify its digest before an executor uses it.

The boundaries are:

- Skill: instructions, examples, templates, and reusable context.
- Executor: the runtime that performs a task, such as Codex or Orca.
- MCP server: a live tool/data integration exposed to an executor.

## Consequences

- Multiple skills can be composed on one task without changing the executor contract.
- Existing executions remain reproducible after new skill versions are registered.
- Third-party Git, archive, and local sources share one catalog model.
- Catalog registration does not imply installation or trust; digest verification is still required.
- Deletion is intentionally omitted while workflow definitions may reference a version.
