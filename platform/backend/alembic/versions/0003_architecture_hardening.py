"""architecture hardening

Revision ID: 0003
Revises: ea7c970068f5
Create Date: 2026-08-15 18:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: str | Sequence[str] | None = "ea7c970068f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ingestion_source_file_hash",
        "ingestion_batches",
        ["source_id", "file_hash"],
    )
    op.create_unique_constraint(
        "uq_golden_sample_run_seed_order",
        "golden_examples",
        ["analysis_run_id", "sampling_seed", "sample_order"],
    )
    op.create_unique_constraint(
        "uq_model_release_evaluation_run",
        "model_releases",
        ["evaluation_run_id"],
    )
    op.create_index(
        "uq_model_releases_single_active",
        "model_releases",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.execute(
        """
        CREATE FUNCTION bearvoice_reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION bearvoice_reject_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION bearvoice_reject_audit_event_mutation()")
    op.drop_index(
        "uq_model_releases_single_active",
        table_name="model_releases",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_constraint(
        "uq_model_release_evaluation_run",
        "model_releases",
        type_="unique",
    )
    op.drop_constraint(
        "uq_golden_sample_run_seed_order",
        "golden_examples",
        type_="unique",
    )
    op.drop_constraint(
        "uq_ingestion_source_file_hash",
        "ingestion_batches",
        type_="unique",
    )
