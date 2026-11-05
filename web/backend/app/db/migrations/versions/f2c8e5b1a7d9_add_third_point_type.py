"""add third point type

Revision ID: f2c8e5b1a7d9
Revises: e1b7d4a9c2f5
Create Date: 2026-11-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2c8e5b1a7d9'
down_revision = 'e1b7d4a9c2f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'third_point_type',
                sa.Integer(),
                nullable=True,
                comment='最后一笔的三买/三卖类型：NULL=无法判断，0=都不是，1=三买，2=三卖',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_third_point',
            'third_point_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_third_point', type_='check')
        batch_op.drop_column('third_point_type')
