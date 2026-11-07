"""add second third combined type

Revision ID: b4e1a7d9c3f2
Revises: a3d9f2c6b8e1
Create Date: 2026-11-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4e1a7d9c3f2'
down_revision = 'a3d9f2c6b8e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'second_third_combined_type',
                sa.Integer(),
                nullable=True,
                comment='最后一笔的二三合买/二三合卖类型：NULL=无法判断，0=都不是，1=二三合买，2=二三合卖',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_second_third_combined',
            'second_third_combined_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_second_third_combined', type_='check')
        batch_op.drop_column('second_third_combined_type')
