"""add brand assets, keep existing installs on their old default timezone

Revision ID: b5f2d8e1a4c6
Revises: a9d2e5f7c3b1
Create Date: 2026-10-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5f2d8e1a4c6'
down_revision = 'a9d2e5f7c3b1'
branch_labels = None
depends_on = None

# Before this release an install with no timezone saved used Australia/Hobart.
# New installs now default to the TIMEZONE env var (UTC if unset), so pin the old
# default on installs that already have locations and never chose one.
PREVIOUS_DEFAULT_TIMEZONE = 'Australia/Hobart'


def upgrade():
    op.create_table('brand_assets',
    sa.Column('key', sa.String(length=32), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )

    bind = op.get_bind()
    has_locations = bind.execute(sa.text("SELECT 1 FROM locations LIMIT 1")).first()
    has_timezone = bind.execute(sa.text("SELECT 1 FROM settings WHERE key = 'timezone'")).first()
    if has_locations and not has_timezone:
        bind.execute(
            sa.text("INSERT INTO settings (key, value) VALUES ('timezone', :value)"),
            {"value": PREVIOUS_DEFAULT_TIMEZONE},
        )


def downgrade():
    op.drop_table('brand_assets')
