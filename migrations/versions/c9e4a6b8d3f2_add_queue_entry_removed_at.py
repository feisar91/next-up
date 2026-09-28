"""add queue_entry removed_at

Revision ID: c9e4a6b8d3f2
Revises: b8d3f5a7c2e1
Create Date: 2026-09-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e4a6b8d3f2'
down_revision = 'b8d3f5a7c2e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('queue_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('queue_entries', schema=None) as batch_op:
        batch_op.drop_column('removed_at')
