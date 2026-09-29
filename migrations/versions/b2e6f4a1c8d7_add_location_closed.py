"""add location closed

Revision ID: b2e6f4a1c8d7
Revises: d1f7b3c5e8a4
Create Date: 2026-09-29 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2e6f4a1c8d7'
down_revision = 'd1f7b3c5e8a4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('closed', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('closed')
