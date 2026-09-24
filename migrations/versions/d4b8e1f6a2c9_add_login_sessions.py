"""add login_sessions table

Revision ID: d4b8e1f6a2c9
Revises: c7e2f4a9d1b3
Create Date: 2026-09-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4b8e1f6a2c9'
down_revision = 'c7e2f4a9d1b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('barber_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('login_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_sessions_barber_id'), ['barber_id'], unique=False)


def downgrade():
    with op.batch_alter_table('login_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_sessions_barber_id'))

    op.drop_table('login_sessions')
