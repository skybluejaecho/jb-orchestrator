"""Disposable signed Webhook endpoint for the process-level notification smoke."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class WebhookSmokeError(RuntimeError):
    """The deterministic Webhook fixture could not be started or observed."""


class WebhookStub:
    def __init__(self, signing_secret: str) -> None:
        self._signing_secret = signing_secret.encode()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.deliveries: list[dict[str, Any]] = []

    @property
    def endpoint_url(self) -> str:
        if self._server is None:
            raise WebhookSmokeError("Webhook stub is not running")
        host_value, port = self._server.server_address[:2]
        host = host_value.decode() if isinstance(host_value, bytes) else host_value
        return f"http://{host}:{port}/events"

    def __enter__(self) -> WebhookStub:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if self.path != "/events":
                    owner._respond(self, 404)
                    return
                length = int(self.headers.get("content-length", "0"))
                body = self.rfile.read(length)
                expected = hmac.new(owner._signing_secret, body, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(
                    self.headers.get("X-JB-Signature-256", ""), f"sha256={expected}"
                ):
                    owner._respond(self, 401)
                    return
                payload = json.loads(body)
                if not isinstance(payload, dict) or not self.headers.get("Idempotency-Key"):
                    owner._respond(self, 400)
                    return
                owner.deliveries.append(payload)
                owner._respond(self, 202, request_id=f"webhook-{len(owner.deliveries)}")

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
    def _respond(
        handler: BaseHTTPRequestHandler, status: int, *, request_id: str | None = None
    ) -> None:
        body = b"{}"
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        if request_id is not None:
            handler.send_header("X-Request-ID", request_id)
        handler.end_headers()
        handler.wfile.write(body)
