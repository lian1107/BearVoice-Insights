"""persist deep semantic signal fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-15 23:55:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing local/legacy signals have no model-derived deep semantics. Keep
    # that boundary explicit with unknown/empty values rather than fabricating
    # issues, causes, or recommendations during migration.
    op.add_column(
        "signals",
        sa.Column(
            "lifecycle_stage",
            sa.String(length=50),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column("signals", sa.Column("issue", sa.Text(), nullable=True))
    op.add_column("signals", sa.Column("latent_need", sa.Text(), nullable=True))
    op.add_column("signals", sa.Column("scenario", sa.Text(), nullable=True))
    op.add_column(
        "signals",
        sa.Column(
            "risk_level",
            sa.String(length=32),
            server_default="unknown",
            nullable=False,
        ),
    )
    for column_name in (
        "root_cause_hypotheses",
        "missing_information",
        "improvement_directions",
        "validation_suggestions",
    ):
        op.add_column(
            "signals",
            sa.Column(
                column_name,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    for column_name in (
        "validation_suggestions",
        "improvement_directions",
        "missing_information",
        "root_cause_hypotheses",
        "risk_level",
        "scenario",
        "latent_need",
        "issue",
        "lifecycle_stage",
    ):
        op.drop_column("signals", column_name)
