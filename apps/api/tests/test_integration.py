"""Explicit real-service tests. Missing credentials skip locally, fail in CI configuration."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from insightrag.core.config import Settings
from insightrag.main import create_app
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def service_url(name):
    file = os.getenv(f"INSIGHTRAG_TEST_{name}_URL_FILE")
    value = os.getenv(f"INSIGHTRAG_TEST_{name}_URL")
    if file:
        value = Path(file).read_text(encoding="utf-8").strip()
    if not value:
        if os.getenv("CI"):
            pytest.fail(f"CI requires real {name} test configuration")
        pytest.skip(f"Real {name} test configuration not supplied")
    return value


async def test_migrated_database_and_restricted_runtime_role():
    engine = create_async_engine(service_url("DATABASE"), hide_parameters=True)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT value FROM platform_metadata WHERE key='schema_version'")
                )
                == "phase6"
            )
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0008_analytics_scope"
            )
            assert not await connection.scalar(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
            )
            assert not await connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            )
            assert not await connection.scalar(
                text("SELECT has_table_privilege(current_user, 'platform_metadata', 'INSERT')")
            )
    finally:
        await engine.dispose()


async def test_real_redis_round_trip():
    redis = Redis.from_url(service_url("REDIS"))
    try:
        assert await redis.ping()
    finally:
        await redis.aclose()


def test_full_readiness_with_real_dependencies():
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=SecretStr(service_url("DATABASE")),
        redis_url=SecretStr(service_url("REDIS")),
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").json() == {
            "status": "ready",
            "dependencies": {"database": "ok", "redis": "ok"},
        }


def test_migration_upgrade_is_idempotent(monkeypatch):
    # Reapply the current schema; never downgrade an arbitrary shared test database.
    url = service_url("MIGRATION_DATABASE")
    monkeypatch.setenv("INSIGHTRAG_MIGRATION_DATABASE_URL", url)
    monkeypatch.delenv("INSIGHTRAG_MIGRATION_DATABASE_URL_FILE", raising=False)
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "head")
