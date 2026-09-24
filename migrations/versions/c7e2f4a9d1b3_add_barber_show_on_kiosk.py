"""add barber show_on_kiosk

Revision ID: c7e2f4a9d1b3
Revises: a3c1e9d4b2f7
Create Date: 2026-09-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e2f4a9d1b3'
down_revision = 'a3c1e9d4b2f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('show_on_kiosk', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.drop_column('show_on_kiosk')
