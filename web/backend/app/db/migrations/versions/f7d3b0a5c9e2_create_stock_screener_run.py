"""Five-column successful screener history.

Revision ID: f7d3b0a5c9e2
Revises: e6c2a9f4b8d1
"""

import sqlalchemy as sa
from alembic import op

revision = "f7d3b0a5c9e2"
down_revision = "e6c2a9f4b8d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_screener_run",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "preset_id", sa.Integer(), sa.ForeignKey("stock_screener_preset.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("version_date", sa.Date(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.UniqueConstraint("preset_id", "frequency", "version_date", name="uq_stock_screener_run_version"),
    )


def downgrade() -> None:
    op.drop_table("stock_screener_run")
