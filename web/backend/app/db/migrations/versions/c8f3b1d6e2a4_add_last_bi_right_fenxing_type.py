"""add last bi right fenxing type

Revision ID: c8f3b1d6e2a4
Revises: b6e2a9c4d8f1
Create Date: 2026-11-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8f3b1d6e2a4'
down_revision = 'b6e2a9c4d8f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'last_bi_right_fenxing_type',
                sa.Integer(),
                nullable=True,
                comment='最后一笔右端点分型：NULL=无法判断，0=无分型（fake），1=底分型，2=顶分型',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_right_fenxing',
            'last_bi_right_fenxing_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_right_fenxing', type_='check')
        batch_op.drop_column('last_bi_right_fenxing_type')
