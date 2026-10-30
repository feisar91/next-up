import os
import secrets
from pathlib import Path

import click

from app import audit, branding, db
from app.login_sessions import end_all_sessions
from app.models import MIN_PASSWORD_LENGTH, Barber

def register_cli(app):
    @app.cli.command("seed-demo")
    @click.option("--password", default="demo-password", show_default=True, help="Password for every demo login.")
    def seed_demo_command(password):
        """Fill an empty database with a made-up shop to try the app out (see app/demo.py).

        Creates two locations, an admin (dana) and five barbers, opening hours, a few
        weeks of past visits for the Metrics page and a live queue for today.
        """
        from app.demo import DemoError, seed_demo

        if len(password) < MIN_PASSWORD_LENGTH:
            raise click.ClickException(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        try:
            counts = seed_demo(password)
        except DemoError as error:
            raise click.ClickException(str(error)) from None
        click.echo(
            f"Created a demo shop with {counts['locations']} locations, {counts['barbers']} logins "
            f"and {counts['visits']} visits. Log in as 'dana' (admin) or 'marco' (barber) "
            f"with the password '{password}'."
        )

    def _reset_demo():
        from app.demo import DemoError
        from app.demo_mode import reset_demo

        try:
            reset_demo()
        except DemoError as error:
            raise click.ClickException(str(error)) from None
        click.echo("Loaded a fresh copy of the demo shop.")

    @app.cli.command("demo-reset")
    def demo_reset():
        """Erase the public demo (DEMO_MODE=true) and load it again, as happens every hour."""
        _reset_demo()

    @app.cli.command("bootstrap")
    def bootstrap():
        """First-run setup, run on every container start. Does nothing once any login exists.

        Normally the owner creates the admin login in the browser (/setup). For an
        unattended install, set $ADMIN_PASSWORD and this creates an `admin` login with
        it instead, to be changed on first login. Creates no locations either way.

        In the public demo (DEMO_MODE=true) it loads a fresh copy of the demo instead.
        """
        from flask import current_app

        if current_app.config["DEMO_MODE"]:
            _reset_demo()
            return
        if Barber.query.first():
            return

        banner = "=" * 60
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            click.echo(
                f"\n{banner}\n"
                f"  No admin login yet. Open the app in your browser to create one.\n"
                f"  Until you do, anyone who can reach the app can create it,\n"
                f"  so do it now.\n"
                f"{banner}\n"
            )
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            raise click.ClickException(f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.")

        admin = Barber(
            name="Admin",
            username="admin",
            is_admin=True,
            must_change_password=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        audit.record("setup.first_admin", "Created the first admin login, Admin (admin), from ADMIN_PASSWORD")

        click.echo(
            f"\n{banner}\n"
            f"  Created the admin login (username: admin) with the password\n"
            f"  from ADMIN_PASSWORD. You'll be asked to change it on first login.\n"
            f"{banner}\n"
        )

    @app.cli.command("set-branding")
    @click.option("--name", help="Shop name.")
    @click.option("--dark", help="Dark colour, e.g. '#1f2933'.")
    @click.option("--accent", help="Accent colour, e.g. '#0d9488'.")
    @click.option("--logo", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Logo image file.")
    @click.option("--icon", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Icon image file.")
    @click.option("--remove-logo", is_flag=True, help="Remove the logo.")
    @click.option("--remove-icon", is_flag=True, help="Remove the icon.")
    def set_branding(name, dark, accent, logo, icon, remove_logo, remove_icon):
        """Set the shop name, colours, logo or icon (same as Admin > Branding).

        Anything not given is left as it is.
        """
        try:
            if name is not None or dark is not None or accent is not None:
                current = branding.get_brand()
                changes = branding.update_identity(
                    current.name if name is None else name,
                    current.dark if dark is None else dark,
                    current.accent if accent is None else accent,
                )
                if changes:
                    summary = branding.change_summary(changes)
                    audit.record("settings.branding", summary)
                    click.echo(summary + ".")
            for kind, path, remove in ((branding.LOGO, logo, remove_logo), (branding.ICON, icon, remove_icon)):
                label = branding.ASSET_LABELS[kind]
                if path:
                    branding.save_asset(kind, path.read_bytes())
                    audit.record(f"settings.{kind}", f"Uploaded a new {label}")
                    click.echo(f"Saved the {label} from {path}.")
                elif remove and branding.remove_asset(kind):
                    audit.record(f"settings.{kind}", f"Removed the {label}")
                    click.echo(f"Removed the {label}.")
        except branding.BrandingError as error:
            raise click.ClickException(str(error)) from None

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
