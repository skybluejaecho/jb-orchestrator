"""Disposable Git and HTTP fixtures for the process-level SCM publication smoke."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class ScmSmokeFixtureError(RuntimeError):
    """A deterministic SCM smoke fixture could not be prepared or observed."""


@dataclass(frozen=True, slots=True)
class ScmSmokeRepository:
    workspace: Path
    repository_url: str
    source_branch: str
    target_branch: str
    workspace_scope: str


def prepare_scm_repository(root: Path, suffix: str) -> ScmSmokeRepository:
    """Create a clean feature worktree whose GitHub URL rewrites to a local bare remote."""

    remote = root / "scm-remote.git"
    workspace = root / "scm-workspace"
    repository_url = "https://github.local/system-smoke/repository.git"
    target_branch = "develop"
    source_branch = f"feature/system-smoke-{suffix}"
    _git(root, "init", "--bare", str(remote))
    _git(root, "init", str(workspace))
    _git(workspace, "config", "user.name", "JB System Smoke")
    _git(workspace, "config", "user.email", "system-smoke@localhost.invalid")
    _git(workspace, "checkout", "-b", target_branch)
    (workspace / "README.md").write_text("# SCM system smoke\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "Initialize smoke repository")
    _git(workspace, "remote", "add", "origin", repository_url)
    _git(workspace, "config", f"url.{remote.resolve().as_uri()}.insteadOf", repository_url)
    _git(workspace, "push", "origin", target_branch)
    _git(workspace, "checkout", "-b", source_branch)
    (workspace / "change.txt").write_text("publish this exact commit\n", encoding="utf-8")
    _git(workspace, "add", "change.txt")
    _git(workspace, "commit", "-m", "Prepare smoke publication")
    return ScmSmokeRepository(
        workspace=workspace.resolve(),
        repository_url=repository_url,
        source_branch=source_branch,
        target_branch=target_branch,
        workspace_scope=f"system-smoke:{suffix}",
    )


def _git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ScmSmokeFixtureError(f"Git fixture command failed: {detail}")
    return completed.stdout.strip()


class GitHubApiStub:
    """Minimal loopback GitHub PR API used only by the disposable system smoke."""

    def __init__(
        self,
        source_branch: str,
        target_branch: str,
        *,
        fail_first_create: bool = False,
    ) -> None:
        self._source_branch = source_branch
        self._target_branch = target_branch
        self._fail_first_create = fail_first_create
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.created = False
        self.create_attempts = 0

    @property
    def api_url(self) -> str:
        if self._server is None:
            raise ScmSmokeFixtureError("GitHub API stub is not running")
        host_value, port = self._server.server_address[:2]
        host = host_value.decode() if isinstance(host_value, bytes) else host_value
        return f"http://{host}:{port}"

    def __enter__(self) -> GitHubApiStub:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.startswith("/repos/system-smoke/repository/pulls?"):
                    owner._respond(self, 200, [])
                    return
                owner._respond(self, 404, {"message": "not found"})

            def do_POST(self) -> None:
                if self.path != "/repos/system-smoke/repository/pulls":
                    owner._respond(self, 404, {"message": "not found"})
                    return
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length))
                if payload.get("head") != owner._source_branch:
                    owner._respond(self, 422, {"message": "unexpected head"})
                    return
                if payload.get("base") != owner._target_branch:
                    owner._respond(self, 422, {"message": "unexpected base"})
                    return
                owner.create_attempts += 1
                if owner._fail_first_create and owner.create_attempts == 1:
                    owner._respond(self, 503, {"message": "temporary smoke failure"})
                    return
                owner.created = True
                owner._respond(
                    self,
                    201,
                    {
                        "number": 53,
                        "html_url": "https://github.local/system-smoke/repository/pull/53",
                        "head": {"ref": owner._source_branch},
                        "base": {"ref": owner._target_branch},
                    },
                )

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @staticmethod
    def _respond(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
        body = json.dumps(payload).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
