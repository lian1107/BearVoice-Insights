"""async model jobs and budget counters

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-15 23:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_budget_counters",
        sa.Column("budget_date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("reserved_calls", sa.Integer(), nullable=False),
        sa.Column("reserved_cost_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_budget_counters")),
        sa.UniqueConstraint(
            "budget_date",
            "provider",
            name="uq_model_budget_date_provider",
        ),
    )
    op.create_table(
        "model_analysis_jobs",
        sa.Column("ingestion_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=200), nullable=False),
        sa.Column("product", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("cluster_count", sa.Integer(), nullable=False),
        sa.Column("opportunity_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("reserved_cost_amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_model_analysis_jobs_analysis_run_id_analysis_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_batch_id"],
            ["ingestion_batches.id"],
            name=op.f("fk_model_analysis_jobs_ingestion_batch_id_ingestion_batches"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_analysis_jobs")),
        sa.UniqueConstraint("idempotency_key", name="uq_model_job_idempotency_key"),
        sa.UniqueConstraint("workflow_id", name=op.f("uq_model_analysis_jobs_workflow_id")),
    )
    op.create_index(
        op.f("ix_model_analysis_jobs_analysis_run_id"),
        "model_analysis_jobs",
        ["analysis_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_analysis_jobs_ingestion_batch_id"),
        "model_analysis_jobs",
        ["ingestion_batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_analysis_jobs_product"),
        "model_analysis_jobs",
        ["product"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_analysis_jobs_provider"),
        "model_analysis_jobs",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_analysis_jobs_status"),
        "model_analysis_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_model_analysis_jobs_status"), table_name="model_analysis_jobs")
    op.drop_index(op.f("ix_model_analysis_jobs_provider"), table_name="model_analysis_jobs")
    op.drop_index(op.f("ix_model_analysis_jobs_product"), table_name="model_analysis_jobs")
    op.drop_index(
        op.f("ix_model_analysis_jobs_ingestion_batch_id"),
        table_name="model_analysis_jobs",
    )
    op.drop_index(
        op.f("ix_model_analysis_jobs_analysis_run_id"),
        table_name="model_analysis_jobs",
    )
    op.drop_table("model_analysis_jobs")
    op.drop_table("model_budget_counters")
