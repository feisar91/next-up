"""add opening hours

Revision ID: e8b3c1d7f4a2
Revises: c4d8a2f6b1e3
Create Date: 2026-09-29 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8b3c1d7f4a2'
down_revision = 'c4d8a2f6b1e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_hours', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('checkin_cutoff_minutes', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('manual_until', sa.DateTime(timezone=True), nullable=True))

    op.create_table('opening_hours',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('weekday', sa.SmallInteger(), nullable=False),
    sa.Column('opens_at', sa.Time(), nullable=False),
    sa.Column('closes_at', sa.Time(), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('location_id', 'weekday')
    )
    with op.batch_alter_table('opening_hours', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_opening_hours_location_id'), ['location_id'], unique=False)

    op.create_table('special_hours',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('opens_at', sa.Time(), nullable=True),
    sa.Column('closes_at', sa.Time(), nullable=True),
    sa.Column('note', sa.String(length=120), nullable=True),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('location_id', 'date')
    )
    with op.batch_alter_table('special_hours', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_special_hours_location_id'), ['location_id'], unique=False)


def downgrade():
    with op.batch_alter_table('special_hours', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_special_hours_location_id'))
    op.drop_table('special_hours')

    with op.batch_alter_table('opening_hours', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_opening_hours_location_id'))
    op.drop_table('opening_hours')

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('manual_until')
        batch_op.drop_column('checkin_cutoff_minutes')
        batch_op.drop_column('auto_hours')
