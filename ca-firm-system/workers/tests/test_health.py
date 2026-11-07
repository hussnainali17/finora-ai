import json
import urllib.error
import urllib.request

from ca_workers.health import make_server, serve_in_thread


def _get(port: int, path: str) -> tuple[int, dict[str, str]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:  # noqa: S310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_live_and_ready_ok() -> None:
    server = make_server(0, lambda: True, host="127.0.0.1")
    serve_in_thread(server)
    port = server.server_address[1]
    try:
        assert _get(port, "/health/live") == (200, {"status": "ok"})
        assert _get(port, "/health/ready") == (200, {"status": "ok"})
    finally:
        server.shutdown()
        server.server_close()


def test_ready_503_when_dependency_down() -> None:
    server = make_server(0, lambda: False, host="127.0.0.1")
    serve_in_thread(server)
    port = server.server_address[1]
    try:
        assert _get(port, "/health/ready")[0] == 503
        assert _get(port, "/health/live")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
