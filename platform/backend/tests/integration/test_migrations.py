import os

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


REQUIRED_TABLES = {
    "sources",
    "ingestion_batches",
    "voice_records",
    "conversation_turns",
    "privacy_findings",
    "analysis_runs",
    "signals",
    "embeddings",
    "taxonomy_versions",
    "clusters",
    "cluster_memberships",
    "taxonomy_revisions",
    "opportunities",
    "opportunity_evidence",
    "review_decisions",
    "competitor_evidence",
    "action_items",
    "outcome_measurements",
    "golden_examples",
    "evaluation_runs",
    "model_releases",
    "audit_events",
}


async def test_initial_migration_creates_enterprise_foundation_tables():
    database_url = os.getenv(
        "BEARVOICE_TEST_DATABASE_URL",
        "postgresql+asyncpg://bearvoice:local-only-change-me@127.0.0.1:55432/bearvoice",
    )
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            table_names = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
            extension = await connection.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
    finally:
        await engine.dispose()

    assert REQUIRED_TABLES <= set(table_names)
    assert extension == "vector"
