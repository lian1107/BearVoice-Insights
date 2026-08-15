"""validated per-voice semantic checkpoints

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15 22:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_voice_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("voice_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_version", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=200), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["voice_record_id"],
            ["voice_records.id"],
            name=op.f("fk_semantic_voice_cache_voice_record_id_voice_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_semantic_voice_cache")),
        sa.UniqueConstraint("cache_key", name="uq_semantic_voice_cache_key"),
    )
    op.create_index(
        op.f("ix_semantic_voice_cache_voice_record_id"),
        "semantic_voice_cache",
        ["voice_record_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_semantic_voice_cache_voice_record_id"),
        table_name="semantic_voice_cache",
    )
    op.drop_table("semantic_voice_cache")
