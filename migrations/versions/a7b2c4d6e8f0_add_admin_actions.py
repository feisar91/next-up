"""add admin_actions table

Revision ID: a7b2c4d6e8f0
Revises: f6a1d8c3e9b4
Create Date: 2026-09-25 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b2c4d6e8f0'
down_revision = 'f6a1d8c3e9b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('admin_actions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('actor_name', sa.String(length=120), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('summary', sa.String(length=500), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['barbers.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_admin_actions_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_admin_actions_created_at'), ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('admin_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_admin_actions_created_at'))
        batch_op.drop_index(batch_op.f('ix_admin_actions_action'))

    op.drop_table('admin_actions')
