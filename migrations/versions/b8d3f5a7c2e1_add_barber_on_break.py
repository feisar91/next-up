"""add barber on_break

Revision ID: b8d3f5a7c2e1
Revises: a7b2c4d6e8f0
Create Date: 2026-09-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d3f5a7c2e1'
down_revision = 'a7b2c4d6e8f0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('on_break', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.drop_column('on_break')
