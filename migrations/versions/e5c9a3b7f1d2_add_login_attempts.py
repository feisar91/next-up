"""add login_attempts table

Revision ID: e5c9a3b7f1d2
Revises: d4b8e1f6a2c9
Create Date: 2026-09-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5c9a3b7f1d2'
down_revision = 'd4b8e1f6a2c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('ip_address', sa.String(length=45), nullable=False),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_attempts_attempted_at'), ['attempted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_attempts_ip_address'), ['ip_address'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_attempts_username'), ['username'], unique=False)


def downgrade():
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_attempts_username'))
        batch_op.drop_index(batch_op.f('ix_login_attempts_ip_address'))
        batch_op.drop_index(batch_op.f('ix_login_attempts_attempted_at'))

    op.drop_table('login_attempts')
