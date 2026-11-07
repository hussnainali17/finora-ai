import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.agents.intake_agent.service import run_intake_loop
from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import client_ip_var, configure_logging, correlation_id_var
from app.db.session import get_sessionmaker
from app.integrations.kafka.publisher import KafkaEventPublisher, get_event_publisher
from app.integrations.storage.s3 import get_object_store
from app.services.outbox import run_relay

logger = logging.getLogger("app")

CORRELATION_HEADER = "X-Request-ID"


async def _run_review_loop(
    session_factory,  # type: ignore[type-arg]
    stop: asyncio.Event,
    interval_seconds: float = 5.0,
) -> None:
    """Background loop: executes 'running' ReviewRuns via Agent 2."""
    from app.services.accounting_review import run_pending_reviews

    while not stop.is_set():
        try:
            async with session_factory() as session:
                await run_pending_reviews(session)
        except Exception:
            logger.exception("review loop iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("backend starting", extra={"env": settings.app_env})
    relay: asyncio.Task[None] | None = None
    stop = asyncio.Event()
    if settings.outbox_relay_enabled:
        # Publishes committed outbox rows (e.g. file.uploaded) to Kafka; safe with many replicas.
        relay = asyncio.create_task(
            run_relay(
                get_sessionmaker(),
                get_event_publisher(),
                interval_seconds=settings.outbox_poll_interval_seconds,
                stop=stop,
            )
        )
    intake: asyncio.Task[None] | None = None
    if settings.intake_enabled:
        # Extracts uploaded files (Agent 1). Independent of Kafka; safe with many replicas.
        intake = asyncio.create_task(
            run_intake_loop(get_sessionmaker(), get_object_store(), settings, stop)
        )
    # Phase 6: execute 'running' ReviewRuns via Agent 2.
    review_loop: asyncio.Task[None] = asyncio.create_task(
        _run_review_loop(get_sessionmaker(), stop)
    )
    yield
    stop.set()
    if intake is not None:
        await intake
    await review_loop
    if relay is not None:
        await relay
        publisher = get_event_publisher()
        if isinstance(publisher, KafkaEventPublisher):
            await publisher.close()
    logger.info("backend stopping")



def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CA Firm System API", version="0.6.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", CORRELATION_HEADER],
    )

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        # Behind Nginx run uvicorn with --proxy-headers and a restricted --forwarded-allow-ips so
        # request.client reflects the real client address.
        ip_token = client_ip_var.set(request.client.host if request.client else None)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
            client_ip_var.reset(ip_token)
        response.headers[CORRELATION_HEADER] = cid
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
