"""add admin_action category

Revision ID: c4d8a2f6b1e3
Revises: b2e6f4a1c8d7
Create Date: 2026-09-29 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d8a2f6b1e3'
down_revision = 'b2e6f4a1c8d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=20), nullable=False, server_default='admin'))
        batch_op.create_index(batch_op.f('ix_admin_actions_category'), ['category'], unique=False)


def downgrade():
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_actions_category'))
        batch_op.drop_column('category')
