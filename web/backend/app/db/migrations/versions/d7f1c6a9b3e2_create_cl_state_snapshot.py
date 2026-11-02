"""create cl state snapshot

Revision ID: d7f1c6a9b3e2
Revises: a90325b8187d
Create Date: 2026-11-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd7f1c6a9b3e2'
down_revision = 'a90325b8187d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'cl_state_snapshot',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='快照行主键'),
        sa.Column(
            'instrument_id',
            sa.Integer(),
            nullable=False,
            comment='关联 instrument.id；标的删除时级联删除',
        ),
        sa.Column('frequency', sa.String(length=16), nullable=False, comment='K 线周期，如 1day、60min'),
        sa.Column('scope', sa.String(length=16), nullable=False, comment='状态构件类型：bi=笔，xianduan=线段'),
        sa.Column('definition_version', sa.Integer(), nullable=False, comment='状态定义版本号，用于区分规则迭代'),
        sa.Column('bar_time', sa.Date(), nullable=True, comment='本次状态判断依据的最后一根 K 线日期'),
        sa.Column(
            'relative_pivot_position',
            sa.Integer(),
            nullable=True,
            comment='相对中枢位置：0=无中枢，1=中枢内，2=中枢下，3=中枢上；NULL=未计算',
        ),
        sa.Column(
            'calculated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            comment='快照写入时间',
        ),
        sa.ForeignKeyConstraint(['instrument_id'], ['instrument.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'frequency', 'scope', name='uq_cl_state_snapshot_identity'),
        sa.CheckConstraint('relative_pivot_position IN (0, 1, 2, 3)', name='ck_cl_state_snapshot_position'),
        comment='缠论笔/线段状态快照宽表，每个标的、周期、构件一行',
    )
    op.create_index(
        'ix_cl_state_snapshot_filter',
        'cl_state_snapshot',
        ['frequency', 'scope', 'relative_pivot_position'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_cl_state_snapshot_filter', table_name='cl_state_snapshot')
    op.drop_table('cl_state_snapshot')
