import os
import secrets

import click

from app import audit, db
from app.login_sessions import end_all_sessions
from app.models import MIN_PASSWORD_LENGTH, Barber, Location

REAL_LOCATIONS = [
    {"name": "Launceston", "slug": "launceston", "address": "George St, Launceston TAS"},
    {"name": "Kings Meadows", "slug": "kings-meadows", "address": "Kings Meadows TAS"},
    {"name": "Youngtown", "slug": "youngtown", "address": "Youngtown TAS"},
]


def ensure_locations():
    for loc in REAL_LOCATIONS:
        if not Location.query.filter_by(slug=loc["slug"]).first():
            db.session.add(Location(**loc))
    db.session.commit()
    return Location.query.filter_by(slug="launceston").first()


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--admin-password", default="changeme", help="Password for the bootstrap admin login.")
    def seed(admin_password):
        """Create the 3 real locations and one bootstrap admin barber login."""
        launceston = ensure_locations()

        if not Barber.query.filter_by(username="admin").first():
            admin = Barber(
                name="Admin",
                username="admin",
                default_location_id=launceston.id,
                is_admin=True,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            click.echo(
                f"Created locations and bootstrap admin login (username: admin, password: {admin_password})"
            )
        else:
            click.echo("Locations ensured. Admin login already existed.")

    @app.cli.command("bootstrap")
    def bootstrap():
        """First-run setup: if no logins exist yet, create the locations and an admin login.

        Uses $ADMIN_PASSWORD if set, otherwise generates a random password. Either way the
        admin must change it on first login. Does nothing once any login exists.
        """
        if Barber.query.first():
            return

        launceston = ensure_locations()
        password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        admin = Barber(
            name="Admin",
            username="admin",
            default_location_id=launceston.id,
            is_admin=True,
            must_change_password=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        banner = "=" * 60
        click.echo(
            f"\n{banner}\n"
            f"  First-run setup complete - created the 3 locations.\n"
            f"  Admin login:  username: admin   password: {password}\n"
            f"  You'll be asked to change this password on first login.\n"
            f"{banner}\n"
        )

    @app.cli.command("reset-admin-password")
    @click.option("--username", default="admin", show_default=True, help="Admin login to reset.")
    @click.option("--password", default=None, help="New temporary password. Random if omitted.")
    def reset_admin_password(username, password):
        """Set a new temporary password on an admin login (for when you're locked out).

        Also reactivates the login if it was deactivated. The admin must choose their
        own password on next login.
        """
        admin = Barber.query.filter_by(username=username).first()
        if not admin:
            raise click.ClickException(f"No login with username '{username}'.")
        if not admin.is_admin:
            raise click.ClickException(f"'{username}' is not an admin login.")
        if password is not None and len(password) < MIN_PASSWORD_LENGTH:
            raise click.ClickException(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

        password = password or secrets.token_urlsafe(12)
        admin.set_password(password)
        admin.must_change_password = True
        admin.active = True
        db.session.commit()
        end_all_sessions(admin)
        audit.record("barber.reset_password", f"Reset the password for {admin.name} from the command line")

        click.echo(f"Password reset for '{username}'. Temporary password: {password}")
        click.echo("They'll be asked to choose their own password on next login.")
