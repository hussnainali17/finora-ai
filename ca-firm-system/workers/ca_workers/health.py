"""Minimal HTTP health server (stdlib only) for container probes."""

import json
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def tcp_reachable(bootstrap_servers: str, timeout: float = 2.0) -> bool:
    """Phase 0 readiness: can we open a TCP connection to the first Kafka broker?"""
    host, _, port = bootstrap_servers.split(",")[0].strip().rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def make_server(
    port: int,
    ready_check: Callable[[], bool],
    host: str = "0.0.0.0",  # noqa: S104
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health/live":
                self._send(200, {"status": "ok"})
            elif self.path == "/health/ready":
                ok = ready_check()
                self._send(200 if ok else 503, {"status": "ok" if ok else "degraded"})
            else:
                self._send(404, {"status": "not_found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # keep probe noise out of logs

    return ThreadingHTTPServer((host, port), Handler)


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    return thread
