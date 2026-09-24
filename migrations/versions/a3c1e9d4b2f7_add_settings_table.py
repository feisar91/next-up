"""add settings table

Revision ID: a3c1e9d4b2f7
Revises: 5fb1cabacb1a
Create Date: 2026-09-21 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c1e9d4b2f7'
down_revision = '5fb1cabacb1a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )


def downgrade():
    op.drop_table('settings')
