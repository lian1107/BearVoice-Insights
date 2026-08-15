import os
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
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
    "golden_reviews",
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


async def test_hardening_migration_enforces_append_only_audit_and_uniqueness():
    database_url = os.getenv(
        "BEARVOICE_TEST_DATABASE_URL",
        "postgresql+asyncpg://bearvoice:local-only-change-me@127.0.0.1:55432/bearvoice",
    )
    engine = create_async_engine(database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    event_id = uuid.uuid4()
    try:
        unique_constraints = await connection.run_sync(
            lambda sync_connection: {
                item["name"]
                for table in (
                    "ingestion_batches",
                    "golden_examples",
                    "model_releases",
                )
                for item in inspect(sync_connection).get_unique_constraints(table)
            }
        )
        active_index = await connection.scalar(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'model_releases' "
                "AND indexname = 'uq_model_releases_single_active'"
            )
        )
        trigger = await connection.scalar(
            text(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgrelid = 'audit_events'::regclass "
                "AND tgname = 'trg_audit_events_append_only'"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, actor_id, action, subject_type, reason) "
                "VALUES (:id, 'tester', 'test.append_only', 'test', 'original')"
            ),
            {"id": event_id},
        )
        savepoint = await connection.begin_nested()
        with pytest.raises(DBAPIError):
            await connection.execute(
                text("UPDATE audit_events SET reason = 'changed' WHERE id = :id"),
                {"id": event_id},
            )
        await savepoint.rollback()
        reason = await connection.scalar(
            text("SELECT reason FROM audit_events WHERE id = :id"),
            {"id": event_id},
        )
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()

    assert {
        "uq_ingestion_source_file_hash",
        "uq_golden_sample_run_seed_order",
        "uq_model_release_evaluation_run",
    } <= unique_constraints
    assert active_index == "uq_model_releases_single_active"
    assert trigger == "trg_audit_events_append_only"
    assert reason == "original"
