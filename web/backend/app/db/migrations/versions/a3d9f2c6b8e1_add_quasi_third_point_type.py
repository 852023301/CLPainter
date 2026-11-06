"""add quasi third point type

Revision ID: a3d9f2c6b8e1
Revises: f2c8e5b1a7d9
Create Date: 2026-11-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3d9f2c6b8e1'
down_revision = 'f2c8e5b1a7d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'quasi_third_point_type',
                sa.Integer(),
                nullable=True,
                comment='最后一笔的类三买/类三卖类型：NULL=无法判断，0=都不是，1=类三买，2=类三卖',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_quasi_third_point',
            'quasi_third_point_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_quasi_third_point', type_='check')
        batch_op.drop_column('quasi_third_point_type')
