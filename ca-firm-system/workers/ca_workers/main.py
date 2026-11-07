"""Worker process entrypoint.

Phase 0: runs the health server and handles graceful shutdown. Kafka consumers,
idempotency, retries and dead-letter handling are added in Phase 5.
"""

import logging
import signal
import threading
from types import FrameType

from ca_workers.config import WorkerSettings
from ca_workers.health import make_server, serve_in_thread, tcp_reachable
from ca_workers.logging_setup import configure_logging

logger = logging.getLogger("worker")


def main() -> None:
    settings = WorkerSettings()
    configure_logging(settings.log_level)

    stop = threading.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("shutdown signal received", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    server = make_server(
        settings.worker_health_port, lambda: tcp_reachable(settings.kafka_bootstrap_servers)
    )
    serve_in_thread(server)
    logger.info("worker started", extra={"health_port": settings.worker_health_port})

    stop.wait()  # Phase 5: replace with the consumer loop

    server.shutdown()
    server.server_close()
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
