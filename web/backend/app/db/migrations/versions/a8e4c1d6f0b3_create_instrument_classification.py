"""Current, timestamp-free instrument classifications.

Revision ID: a8e4c1d6f0b3
Revises: f7d3b0a5c9e2
"""

import sqlalchemy as sa
from alembic import op

revision = "a8e4c1d6f0b3"
down_revision = "f7d3b0a5c9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_classification",
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instrument.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sw_l1_code", sa.String(16), nullable=True),
        sa.Column("sw_l1_name", sa.String(128), nullable=True),
        sa.Column("sw_l2_code", sa.String(16), nullable=True),
        sa.Column("sw_l2_name", sa.String(128), nullable=True),
        sa.Column("sw_l3_code", sa.String(16), nullable=True),
        sa.Column("sw_l3_name", sa.String(128), nullable=True),
        sa.Column("concepts", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("regions", sa.JSON(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("instrument_classification")
