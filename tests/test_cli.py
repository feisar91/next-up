from app import db
from app.models import Barber


def test_reset_admin_password_sets_given_password(app, admin_barber):
    result = app.test_cli_runner().invoke(
        args=["reset-admin-password", "--username", "morgan", "--password", "newpass123"]
    )

    assert result.exit_code == 0, result.output
    assert "newpass123" in result.output
    admin = db.session.get(Barber, admin_barber["id"])
    assert admin.check_password("newpass123")
    assert admin.must_change_password is True


def test_reset_admin_password_generates_one_and_reactivates(app, admin_barber):
    admin = db.session.get(Barber, admin_barber["id"])
    admin.active = False
    db.session.commit()

    result = app.test_cli_runner().invoke(args=["reset-admin-password", "--username", "morgan"])

    assert result.exit_code == 0, result.output
    password = result.output.split("Temporary password: ")[1].split()[0]
    admin = db.session.get(Barber, admin_barber["id"])
    assert admin.check_password(password)
    assert admin.active is True


def test_reset_admin_password_rejects_non_admin(app, barber):
    result = app.test_cli_runner().invoke(args=["reset-admin-password", "--username", "alex"])

    assert result.exit_code != 0
    assert "not an admin" in result.output
    assert db.session.get(Barber, barber["id"]).check_password("password123")


def test_reset_admin_password_rejects_unknown_user(app):
    result = app.test_cli_runner().invoke(args=["reset-admin-password", "--username", "nobody"])

    assert result.exit_code != 0
    assert "No login" in result.output


def test_reset_admin_password_rejects_short_password(app, admin_barber):
    result = app.test_cli_runner().invoke(
        args=["reset-admin-password", "--username", "morgan", "--password", "short"]
    )

    assert result.exit_code != 0
    assert db.session.get(Barber, admin_barber["id"]).check_password("password123")
