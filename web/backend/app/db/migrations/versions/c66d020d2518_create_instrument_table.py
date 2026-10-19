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

    op.create_table('watchlist_board',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('watchlist_item',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('board_id', sa.Integer(), sa.ForeignKey('watchlist_board.id', ondelete='CASCADE'), nullable=False),
    sa.Column('instrument_id', sa.Integer(), sa.ForeignKey('instrument.id', ondelete='CASCADE'), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('board_id', 'instrument_id', name='uq_watchlist_item')
    )
    op.create_index('ix_watchlist_item_board_order', 'watchlist_item', ['board_id', 'sort_order'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_watchlist_item_board_order', table_name='watchlist_item')
    op.drop_table('watchlist_item')
    op.drop_table('watchlist_board')
    op.drop_table('instrument')
