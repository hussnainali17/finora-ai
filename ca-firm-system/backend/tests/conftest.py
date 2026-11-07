import os

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
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
