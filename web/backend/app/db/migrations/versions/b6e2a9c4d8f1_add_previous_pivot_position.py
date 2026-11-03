"""add previous pivot position

Revision ID: b6e2a9c4d8f1
Revises: f4b8d2e6a1c7
Create Date: 2026-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b6e2a9c4d8f1'
down_revision = 'f4b8d2e6a1c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'relative_previous_pivot_position',
                sa.Integer(),
                nullable=True,
                comment='相对前一趋势最后一个扩展中枢的位置：0=无扩展中枢，1=中枢内，2=中枢下，3=中枢上；NULL=未计算',
            )
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_previous_position',
            'relative_previous_pivot_position IN (0, 1, 2, 3)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_previous_position', type_='check')
        batch_op.drop_column('relative_previous_pivot_position')
