import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# Set required configuration BEFORE the app is imported. Test-only dummy values.
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
        "REDIS_URL": "redis://:test@localhost:6379/0",
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:29092",
        "MINIO_ENDPOINT": "http://localhost:9000",
        "MINIO_ACCESS_KEY": "test-access",
        "MINIO_SECRET_KEY": "test-secret",
        "LITELLM_BASE_URL": "http://localhost:4000",
        "LITELLM_API_KEY": "sk-test",
        "JWT_SECRET": "test-only-jwt-secret-0123456789-abcdefghij",
        "LOGIN_MAX_FAILED_ATTEMPTS": "5",
        "OUTBOX_RELAY_ENABLED": "false",  # tests drive the relay explicitly
        "MAX_UPLOAD_BYTES": "1048576",  # 1 MiB so size-limit tests stay fast
    }
)

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.permissions import ACCOUNTANT, CA_REVIEWER, CLIENT_USER, FIRM_ADMIN  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.integrations.kafka.publisher import EventEnvelope, get_event_publisher  # noqa: E402
from app.integrations.storage.s3 import S3ObjectStore, get_object_store  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Client, Firm, User, UserClientAccess  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
PASSWORD = "Correct-Horse-Battery-9"
_PASSWORD_HASH = hash_password(PASSWORD)  # hashed once; argon2 is deliberately slow


@pytest.fixture
def client() -> TestClient:
    """Synchronous client for tests that need no database (health, config)."""
    return TestClient(create_app())


# ----------------------------------------------------------------------------- database
# Database tests need a real PostgreSQL (composite FKs, exclusion constraints and triggers are
# part of what is being tested). Set TEST_DATABASE_URL to a DISPOSABLE database: the schema is
# dropped and rebuilt from the migrations at the start of the test session.


def _test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set - skipping PostgreSQL-backed tests")
    return url


@pytest.fixture(scope="session")
def migrated_db_url() -> Iterator[str]:
    url = _test_db_url()
    env = {**os.environ, "DATABASE_URL": url}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
    yield url


@pytest_asyncio.fixture
async def session_factory(migrated_db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        migrated_db_url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


# ----------------------------------------------------------------------------- S3 + Kafka fakes
# Object storage is a REAL S3 protocol server (moto) so uploads/downloads exercise boto3 for real.
# Kafka is replaced by an in-memory publisher (no broker in the test environment).

BUCKET = "ca-firm-test"


@pytest.fixture(scope="session")
def s3_server() -> Iterator[str]:
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def store(s3_server: str) -> S3ObjectStore:
    import boto3

    boto3.client(
        "s3",
        endpoint_url=s3_server,
        aws_access_key_id="k",
        aws_secret_access_key="s",
        region_name="us-east-1",
    ).create_bucket(Bucket=BUCKET)  # idempotent for moto
    return S3ObjectStore(
        endpoint=s3_server, access_key="k", secret_key="s", bucket=BUCKET, region="us-east-1"
    )


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, EventEnvelope]] = []
        self.fail_next = 0

    async def publish(self, topic: str, key: str, event: EventEnvelope) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise ConnectionError("broker unavailable: kafka.internal:9092 secret-host")
        self.published.append((topic, key, event))


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest_asyncio.fixture
async def api(
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    publisher: FakePublisher,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_object_store] = lambda: store
    app.dependency_overrides[get_event_publisher] = lambda: publisher

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except BaseException:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _session
    transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 4321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


# ----------------------------------------------------------------------------- factories


class World:
    """Two firms with a mix of users and clients, created straight through the ORM."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self.tag = uuid.uuid4().hex[:8]

    async def firm(self, name: str = "Firm") -> Firm:
        async with self._sf() as s:
            firm = Firm(name=f"{name} {self.tag}", slug=f"{name.lower()}-{uuid.uuid4().hex[:10]}")
            s.add(firm)
            await s.commit()
            return firm

    async def user(self, firm: Firm, role: str, *, label: str = "", active: bool = True) -> User:
        async with self._sf() as s:
            user = User(
                firm_id=firm.id,
                email=f"{role}.{label}{uuid.uuid4().hex[:8]}@example.com",
                full_name=f"{role} {label}".strip(),
                role_key=role,
                password_hash=_PASSWORD_HASH,
                is_active=active,
            )
            s.add(user)
            await s.commit()
            return user

    async def client(self, firm: Firm, name: str = "Client") -> Client:
        async with self._sf() as s:
            c = Client(
                firm_id=firm.id,
                code=f"C-{uuid.uuid4().hex[:8]}",
                name=f"{name} {uuid.uuid4().hex[:4]}",
            )
            s.add(c)
            await s.commit()
            return c

    async def assign(self, user: User, client: Client) -> None:
        async with self._sf() as s:
            s.add(UserClientAccess(user_id=user.id, client_id=client.id, firm_id=client.firm_id))
            await s.commit()


@pytest.fixture
def world(session_factory: async_sessionmaker[AsyncSession]) -> World:
    return World(session_factory)


async def login(api: httpx.AsyncClient, user: User, password: str = PASSWORD) -> dict[str, str]:
    """Logs in and returns Authorization headers."""
    resp = await api.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


__all__ = ["ACCOUNTANT", "CA_REVIEWER", "CLIENT_USER", "FIRM_ADMIN", "PASSWORD", "World", "login"]
