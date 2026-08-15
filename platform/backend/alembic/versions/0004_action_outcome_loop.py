"""action outcome loop

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-15 22:10:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outcome_measurements",
        sa.Column("metric_definition", sa.Text(), nullable=False, server_default="TBD"),
    )
    op.add_column(
        "outcome_measurements",
        sa.Column("unit", sa.String(length=80), nullable=False, server_default="TBD"),
    )
    op.add_column(
        "outcome_measurements",
        sa.Column(
            "observation_window",
            sa.String(length=200),
            nullable=False,
            server_default="TBD",
        ),
    )
    op.add_column(
        "outcome_measurements",
        sa.Column(
            "recorded_by",
            sa.String(length=200),
            nullable=False,
            server_default="historical-import",
        ),
    )


def downgrade() -> None:
    op.drop_column("outcome_measurements", "recorded_by")
    op.drop_column("outcome_measurements", "observation_window")
    op.drop_column("outcome_measurements", "unit")
    op.drop_column("outcome_measurements", "metric_definition")
