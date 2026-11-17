"""Alembic environment (async). The URL comes from the environment or backend .env file."""

import asyncio
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.config import _async_database_url_and_connect_args
from app.db.base import Base

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

config = context.config
target_metadata = Base.metadata


def _database_connection_settings() -> tuple[str, dict[str, dict[str, str]]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return _async_database_url_and_connect_args(url)


def run_migrations_offline() -> None:
    url, _ = _database_connection_settings()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url, connect_args = _database_connection_settings()
    engine = create_async_engine(url, connect_args=connect_args, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
