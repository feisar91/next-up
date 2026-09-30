"""add location announcement

Revision ID: a9d2e5f7c3b1
Revises: e8b3c1d7f4a2
Create Date: 2026-09-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9d2e5f7c3b1'
down_revision = 'e8b3c1d7f4a2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('announcement', sa.String(length=140), nullable=True))
        batch_op.add_column(sa.Column('announcement_until', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('announcement_until')
        batch_op.drop_column('announcement')
