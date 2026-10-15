'''add instrument listing dates

Revision ID: 390ccd10127d
Revises: c66d020d2518
Create Date: 2026-10-15 15:57:32.915727

'''
from alembic import op
import sqlalchemy as sa


revision = '390ccd10127d'
down_revision = 'c66d020d2518'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('instrument', schema=None) as batch_op:
        batch_op.add_column(sa.Column('list_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('delist_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('instrument', schema=None) as batch_op:
        batch_op.drop_column('delist_date')
        batch_op.drop_column('list_date')
