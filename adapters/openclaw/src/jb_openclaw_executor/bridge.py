"""Async subprocess boundary for the official Node Gateway client."""

import asyncio
import json
from pathlib import Path
from typing import Any, Protocol


class OpenClawBridgeError(RuntimeError):
    """The Gateway bridge failed or returned an invalid response."""


class OpenClawBridge(Protocol):
    async def inspect(self) -> dict[str, Any]: ...

    async def start(self, request: dict[str, Any]) -> dict[str, Any]: ...

    async def wait(self, run_id: str, timeout_ms: int) -> dict[str, Any]: ...

    async def cancel(self, run_id: str) -> dict[str, Any]: ...


class OpenClawBridgeClient:
    def __init__(self, bridge_path: Path, *, node_executable: str = "node") -> None:
        self._bridge_path = bridge_path.resolve()
        self._node_executable = node_executable

    async def inspect(self) -> dict[str, Any]:
        return await self._invoke({"action": "inspect"}, timeout_seconds=35)

    async def start(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self._invoke({"action": "start", "input": request}, timeout_seconds=35)

    async def wait(self, run_id: str, timeout_ms: int) -> dict[str, Any]:
        return await self._invoke(
            {"action": "wait", "runId": run_id, "timeoutMs": timeout_ms},
            timeout_seconds=(timeout_ms / 1_000) + 10,
        )

    async def cancel(self, run_id: str) -> dict[str, Any]:
        return await self._invoke({"action": "cancel", "runId": run_id}, timeout_seconds=15)

    async def _invoke(self, request: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        if not self._bridge_path.is_file():
            raise OpenClawBridgeError(f"OpenClaw bridge not found: {self._bridge_path}")
        process = await asyncio.create_subprocess_exec(
            self._node_executable,
            str(self._bridge_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                stdout, stderr = await process.communicate(
                    json.dumps(request, separators=(",", ":")).encode()
                )
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip() or "unknown bridge error"
            raise OpenClawBridgeError(detail)
        try:
            response = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenClawBridgeError("OpenClaw bridge returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise OpenClawBridgeError("OpenClaw bridge response must be an object")
        return response
