import secrets

from flask import Blueprint, abort, render_template

from app.models import Location

display_bp = Blueprint("display", __name__)


@display_bp.route("/display/<location_slug>/<token>")
def show(location_slug, token):
    location = Location.query.filter_by(slug=location_slug, active=True).first()
    if not location or not secrets.compare_digest(token, location.display_token):
        abort(404)
    return render_template("display.html", location=location, token=token)
