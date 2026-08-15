from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from bearvoice.config import Settings
from bearvoice.db import Base
from bearvoice.domain import models  # noqa: F401


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
