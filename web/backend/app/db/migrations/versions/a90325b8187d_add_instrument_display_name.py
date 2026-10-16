"""add instrument display name

Revision ID: a90325b8187d
Revises: 390ccd10127d
Create Date: 2026-10-15 19:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a90325b8187d'
down_revision = '390ccd10127d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('instrument', schema=None) as batch_op:
        batch_op.add_column(sa.Column('display_name', sa.String(length=128), nullable=True))
    op.execute("UPDATE instrument SET display_name = name")
    with op.batch_alter_table('instrument', schema=None) as batch_op:
        batch_op.alter_column('display_name', existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('instrument', schema=None) as batch_op:
        batch_op.drop_column('display_name')
