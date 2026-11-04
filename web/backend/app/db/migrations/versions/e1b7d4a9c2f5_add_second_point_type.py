"""add second point type

Revision ID: e1b7d4a9c2f5
Revises: d9a4c2e7f1b6
Create Date: 2026-11-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1b7d4a9c2f5'
down_revision = 'd9a4c2e7f1b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'second_point_type',
                sa.Integer(),
                nullable=True,
                comment='最后一笔的二买/二卖类型：NULL=无法判断，0=都不是，1=二买，2=二卖',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_second_point',
            'second_point_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_second_point', type_='check')
        batch_op.drop_column('second_point_type')
