"""add barber on_duty_since

Revision ID: d1f7b3c5e8a4
Revises: c9e4a6b8d3f2
Create Date: 2026-09-28 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f7b3c5e8a4'
down_revision = 'c9e4a6b8d3f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('on_duty_since', sa.DateTime(timezone=True), nullable=True))
    # Barbers already on duty start their clock now, rather than being taken
    # off the kiosk the moment this deploys.
    op.execute("UPDATE barbers SET on_duty_since = CURRENT_TIMESTAMP WHERE on_duty_location_id IS NOT NULL")


def downgrade():
    with op.batch_alter_table('barbers', schema=None) as batch_op:
        batch_op.drop_column('on_duty_since')
