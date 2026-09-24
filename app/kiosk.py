import secrets

from flask import Blueprint, abort, render_template, request

from app import db
from app.models import Location, QueueEntry
from app.sockets import broadcast_queue, kiosk_barbers, queue_state

kiosk_bp = Blueprint("kiosk", __name__)


def _get_authorized_location(location_slug, token):
    location = Location.query.filter_by(slug=location_slug, active=True).first()
    if not location or not secrets.compare_digest(token, location.kiosk_token):
        abort(404)
    return location


@kiosk_bp.route("/kiosk/<location_slug>/<token>", methods=["GET", "POST"])
def check_in(location_slug, token):
    location = _get_authorized_location(location_slug, token)
    barbers = kiosk_barbers(location)

    confirmation = None

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        # Only accept a barber the kiosk actually offered; anything else (hidden,
        # off duty, or a tampered form) falls back to "no preference".
        preferred_barber_id = request.form.get("preferred_barber_id", "")
        preferred_barber = next((b for b in barbers if str(b.id) == preferred_barber_id), None)

        if customer_name:
            entry = QueueEntry(
                location_id=location.id,
                customer_name=customer_name,
                preferred_barber_id=preferred_barber.id if preferred_barber else None,
                status=QueueEntry.STATUS_WAITING,
            )
            db.session.add(entry)
            db.session.commit()

            broadcast_queue(location)

            position = len(queue_state(location)["waiting"])
            confirmation = {"name": customer_name, "position": position}

    return render_template(
        "kiosk.html",
        location=location,
        token=token,
        barbers=barbers,
        confirmation=confirmation,
    )
