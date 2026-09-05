# GitHub publisher adapter

This package implements the jb_orchestrator.scm_publishers entry point named github. It publishes
one already committed managed-worktree branch and creates or reuses an open GitHub pull request.

## Configuration

The adapter reads its credentials and filesystem authority from its own process environment:

    JB_GITHUB_TOKEN=<fine-grained-token>
    JB_GITHUB_WORKSPACE_ROOTS=["C:\\worktrees\\jb-orchestrator"]

Optional settings:

    JB_GITHUB_API_URL=https://api.github.com
    JB_GITHUB_WEB_HOST=github.com
    JB_GITHUB_API_VERSION=2026-03-10
    JB_GITHUB_GIT_EXECUTABLE=git
    JB_GITHUB_REMOTE_NAME=origin
    JB_GITHUB_GIT_TIMEOUT_SECONDS=120
    JB_GITHUB_HTTP_TIMEOUT_SECONDS=30

The API token needs Pull requests repository permission with write access. The Git push uses the
remote's existing SSH key or Git credential helper; the API token is deliberately not inserted into
Git command arguments or remote URLs. That Git identity needs permission to push the source branch.

For GitHub Enterprise, set both API URL and web host. API traffic must use HTTPS.

## Run

Install the adapter into the SCM worker process and verify discovery:

    uv run --with-editable . --with-editable adapters/github jb-scm-worker --list-publishers

Then start one worker for the exact opaque scope assigned by the OpenClaw workspace manager:

    uv run --with-editable . --with-editable adapters/github jb-scm-worker --workspace-scope <workspace-scope>

## Safety boundary

Before any remote mutation, the adapter:

- resolves the worktree path below an explicitly configured workspace root
- confirms the path is the Git worktree root
- validates source and target Git ref names
- requires the current branch to equal the requested source branch
- requires a clean worktree
- confirms the configured Git remote identifies the requested GitHub repository
- resolves HEAD and pushes that exact commit with a non-force refspec

It then queries open pull requests for the exact owner, head, and base. An existing pull request is
reused. If creation returns HTTP 422, the adapter checks once more for a concurrently created pull
request before failing. It never merges, force-pushes, deletes a branch, or cleans a worktree.
