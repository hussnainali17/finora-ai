"""Worker process entrypoint — Phase 5.

Starts all Kafka consumers as async tasks, runs until SIGTERM/SIGINT,
then cleanly stops each consumer (commits current offsets, closes connections)
and shuts down the health server.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from types import FrameType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ca_workers.config import WorkerSettings
from ca_workers.consumers.file_processing_consumer import FileProcessingConsumer
from ca_workers.consumers.review_consumer import ReviewConsumer
from ca_workers.health import make_server, serve_in_thread, tcp_reachable
from ca_workers.logging_setup import configure_logging

logger = logging.getLogger("worker")


def _build_session_factory(settings: WorkerSettings) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        settings.async_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    return async_sessionmaker(engine, expire_on_commit=False)


async def _run_all_consumers(settings: WorkerSettings, stop: asyncio.Event) -> None:
    session_factory = _build_session_factory(settings)

    consumers = [
        FileProcessingConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            session_factory=session_factory,
            max_retries=settings.kafka_max_retries,
            retry_backoff_ms=settings.kafka_retry_backoff_ms,
            auto_offset_reset=settings.kafka_auto_offset_reset,
            session_timeout_ms=settings.kafka_session_timeout_ms,
            max_poll_interval_ms=settings.kafka_max_poll_interval_ms,
        ),
        ReviewConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            session_factory=session_factory,
            max_retries=settings.kafka_max_retries,
            retry_backoff_ms=settings.kafka_retry_backoff_ms,
            auto_offset_reset=settings.kafka_auto_offset_reset,
            session_timeout_ms=settings.kafka_session_timeout_ms,
            max_poll_interval_ms=settings.kafka_max_poll_interval_ms,
        ),
    ]

    tasks = [asyncio.create_task(c.run(stop), name=f"consumer-{c.topic}") for c in consumers]
    logger.info("all consumers started", extra={"count": len(consumers)})

    # Wait until stop is requested
    await stop.wait()

    logger.info("stop signal received — waiting for consumer tasks to finish")
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("all consumer tasks finished")


def main() -> None:
    settings = WorkerSettings()
    configure_logging(settings.log_level)

    # Threading event for the health server thread (not asyncio)
    thread_stop = threading.Event()

    def _request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("shutdown signal received", extra={"signal": signum})
        thread_stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    # Health server: responds 200 when Kafka is reachable
    server = make_server(
        settings.worker_health_port,
        lambda: tcp_reachable(settings.kafka_bootstrap_servers),
    )
    serve_in_thread(server)
    logger.info("worker started", extra={"health_port": settings.worker_health_port})

    async def _run() -> None:
        stop = asyncio.Event()

        # Bridge threading stop event into asyncio
        def _set_async_stop() -> None:
            thread_stop.wait()
            stop.set()

        bridge = threading.Thread(target=_set_async_stop, daemon=True)
        bridge.start()

        await _run_all_consumers(settings, stop)

    asyncio.run(_run())

    server.shutdown()
    server.server_close()
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
