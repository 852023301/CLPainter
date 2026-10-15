'''create instrument table

Revision ID: c66d020d2518
Revises: 
Create Date: 2026-10-15 00:17:00.823038

'''
from alembic import op
import sqlalchemy as sa


revision = 'c66d020d2518'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('instrument',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('price_precision', sa.Integer(), nullable=False),
    sa.Column('market', sa.String(length=16), nullable=False),
    sa.Column('asset_class', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('market', 'asset_class', 'code', name='uq_instrument_identity')
    )


def downgrade() -> None:
    op.drop_table('instrument')
