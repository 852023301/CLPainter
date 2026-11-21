"""Create persistent stock screener presets.

Revision ID: e6c2a9f4b8d1
Revises: b4e1a7d9c3f2
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa


revision = "e6c2a9f4b8d1"
down_revision = "b4e1a7d9c3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_screener_preset",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_stock_screener_preset_name"),
    )


def downgrade() -> None:
    op.drop_table("stock_screener_preset")
