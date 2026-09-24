"""add kiosk/display last seen to locations

Revision ID: f6a1d8c3e9b4
Revises: e5c9a3b7f1d2
Create Date: 2026-09-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a1d8c3e9b4'
down_revision = 'e5c9a3b7f1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kiosk_last_seen_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('display_last_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('display_last_seen_at')
        batch_op.drop_column('kiosk_last_seen_at')
