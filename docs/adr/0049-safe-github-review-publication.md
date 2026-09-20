# ADR 0049: Publish GitHub reviews without force, merge, or credential injection

- Status: Accepted
- Date: 2026-09-05

## Context

ORCH-051 can execute installed SCM publishers, but no concrete provider exists. GitHub is the first
target because this repository and its current review flow use GitHub pull requests. Publication
combines two remote effects: pushing an exact local commit and creating content through the GitHub
REST API.

Passing a token in a Git URL or command argument risks disclosure through process listings, errors,
and persisted configuration. Blind retries can also create duplicate pull requests, while force
pushes can overwrite work published by another person.

## Decision

Provide jb-github-publisher as a separately installed adapter. It accepts only HTTPS, SSH, and
SCP-like remotes for one configured GitHub host and rejects URLs containing credentials, queries,
or fragments.

Before pushing, resolve the worktree below an explicit root allowlist and verify that it is the Git
top level, is clean, is on the exact requested source branch, and has a remote matching the trusted
Project repository. Resolve HEAD once and push that exact commit to the source ref without force.
Interactive Git credential prompts are disabled. Git authentication remains the responsibility of
the remote's SSH key or credential helper and is separate from the API token.

Use GitHub's versioned REST API serially. Query the exact open head/base pair before creation and
reuse it when present. Create a pull request only when absent. If creation returns HTTP 422, query
once more to recover a concurrent-create race; otherwise fail without retrying a mutation.

Accept a successful API response only when it includes a positive pull-request number, an HTTPS
review URL on the configured GitHub host, and the exact source and target refs. Error messages retain
only the HTTP status and GitHub request ID, not response bodies or authorization headers.

The API token and workspace allowlist are required adapter-owned environment settings. The token is
never passed to Git, the Control Plane, Jarvis, or the publication ledger.

## Consequences

- ORCH-051 can now produce a real GitHub pull-request URL.
- Non-fast-forward branch conflicts fail instead of overwriting remote history.
- A clean committed branch and non-interactive Git authentication are operational prerequisites.
- Fine-grained tokens can be limited to Pull requests write access for the allowed repository.
- GitHub Enterprise is supported by explicit API URL and web-host configuration.
- Automated merge, force-push, remote branch deletion, and local cleanup remain unsupported.
