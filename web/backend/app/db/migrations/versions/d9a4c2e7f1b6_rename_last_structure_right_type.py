"""rename last structure right type

Revision ID: d9a4c2e7f1b6
Revises: c8f3b1d6e2a4
Create Date: 2026-11-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9a4c2e7f1b6'
down_revision = 'c8f3b1d6e2a4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_right_fenxing', type_='check')
        batch_op.alter_column(
            'last_bi_right_fenxing_type',
            new_column_name='last_structure_right_type',
            existing_type=sa.Integer(),
            existing_nullable=True,
            existing_comment='最后一笔右端点分型：NULL=无法判断，0=无分型（fake），1=底分型，2=顶分型',
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_right_structure',
            'last_structure_right_type IN (0, 1, 2)',
        )


def downgrade() -> None:
    with op.batch_alter_table('cl_state_snapshot', schema=None) as batch_op:
        batch_op.drop_constraint('ck_cl_state_snapshot_right_structure', type_='check')
        batch_op.alter_column(
            'last_structure_right_type',
            new_column_name='last_bi_right_fenxing_type',
            existing_type=sa.Integer(),
            existing_nullable=True,
            existing_comment='当前 scope 最后一个构件的右侧类型：NULL=无法判断，0=无分型（fake），1=底分型，2=顶分型',
        )
        batch_op.create_check_constraint(
            'ck_cl_state_snapshot_right_fenxing',
            'last_bi_right_fenxing_type IN (0, 1, 2)',
        )
