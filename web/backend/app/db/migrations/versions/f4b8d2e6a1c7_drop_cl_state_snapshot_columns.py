"""drop cl state snapshot columns

Revision ID: f4b8d2e6a1c7
Revises: d7f1c6a9b3e2
Create Date: 2026-11-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4b8d2e6a1c7'
down_revision = 'd7f1c6a9b3e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_column('bar_time')
        batch_op.drop_column('definition_version')


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('definition_version', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(sa.Column('bar_time', sa.Date(), nullable=True))
