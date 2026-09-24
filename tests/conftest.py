import pytest
from flask import g

from app import create_app, db
from app.models import Barber, Location
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)

    # This fixture keeps one app context open for the whole test, and test requests
    # reuse it, so Flask-Login's per-context user cache (g._login_user) would leak
    # between requests and between test clients. Real requests each get a fresh
    # context, so clear it first thing (ahead of the app's own before_request hooks).
    def reset_login_cache():
        g.pop("_login_user", None)

    app.before_request_funcs.setdefault(None, []).insert(0, reset_login_cache)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def locations(app):
    with app.app_context():
        launceston = Location(name="Launceston", slug="launceston")
        kings_meadows = Location(name="Kings Meadows", slug="kings-meadows")
        db.session.add_all([launceston, kings_meadows])
        db.session.commit()
        return {"launceston": launceston.id, "kings-meadows": kings_meadows.id}


@pytest.fixture()
def barber(app, locations):
    with app.app_context():
        b = Barber(name="Alex", username="alex", default_location_id=locations["launceston"])
        b.set_password("password123")
        db.session.add(b)
        db.session.commit()
        return {"id": b.id, "username": "alex", "password": "password123"}


@pytest.fixture()
def other_location_barber(app, locations):
    with app.app_context():
        b = Barber(name="Sam", username="sam", default_location_id=locations["kings-meadows"])
        b.set_password("password123")
        db.session.add(b)
        db.session.commit()
        return {"id": b.id, "username": "sam", "password": "password123"}


@pytest.fixture()
def floating_barber(app, locations):
    with app.app_context():
        b = Barber(name="Casey", username="casey", default_location_id=None)
        b.set_password("password123")
        db.session.add(b)
        db.session.commit()
        return {"id": b.id, "username": "casey", "password": "password123"}


@pytest.fixture()
def admin_barber(app, locations):
    with app.app_context():
        b = Barber(name="Morgan Admin", username="morgan", default_location_id=locations["launceston"], is_admin=True)
        b.set_password("password123")
        db.session.add(b)
        db.session.commit()
        return {"id": b.id, "username": "morgan", "password": "password123"}


def login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=True
    )


def kiosk_url(app, slug):
    with app.app_context():
        location = Location.query.filter_by(slug=slug).first()
        return f"/kiosk/{slug}/{location.kiosk_token}"


def display_url(app, slug):
    with app.app_context():
        location = Location.query.filter_by(slug=slug).first()
        return f"/display/{slug}/{location.display_token}"
