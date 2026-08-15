from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from bearvoice.config import Settings
from bearvoice.db import Base
from bearvoice.db import get_db_session
from bearvoice.domain import models  # noqa: F401
from bearvoice.main import create_app
from bearvoice.security.auth import issue_dev_token


DEV_AUTH_KEY = "bearvoice-development-test-signing-key"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def kettle_csv(repo_root: Path) -> Path:
    return repo_root / "vault/raw/20260815-赛题资料/天猫咨询原声-1500条.csv"


@pytest.fixture
async def db_session():
    engine = create_async_engine(Settings().database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    table_names = ", ".join(
        f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
    )
    await connection.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    return Settings(
        dev_auth_enabled=True,
        dev_auth_signing_key=DEV_AUTH_KEY,
        object_store_root=str(tmp_path / "objects"),
    )


@pytest.fixture
async def api_client(db_session, api_settings):
    app = create_app(api_settings)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def management_token(api_settings: Settings) -> str:
    return issue_dev_token(
        api_settings,
        subject="management-1",
        roles=("management",),
        product_lines=(),
    )


@pytest.fixture
def reviewer_token(api_settings: Settings) -> str:
    return issue_dev_token(
        api_settings,
        subject="reviewer-1",
        roles=("quality_reviewer",),
        product_lines=("养生壶",),
    )


@pytest.fixture
def admin_token(api_settings: Settings) -> str:
    return issue_dev_token(
        api_settings,
        subject="admin-1",
        roles=("admin",),
        product_lines=("养生壶",),
    )
