from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.metrics import compute_metrics
from app.models import QueueEntry
from app.settings import DEFAULT_TIMEZONE, get_timezone_name
from tests.conftest import login

HOBART = ZoneInfo("Australia/Hobart")


def add_entry(location_id, checked_in_at, status=QueueEntry.STATUS_DONE, wait=10, service=20, **kwargs):
    called_at = checked_in_at + timedelta(minutes=wait) if status != QueueEntry.STATUS_WAITING else None
    completed_at = called_at + timedelta(minutes=service) if status == QueueEntry.STATUS_DONE else None
    if status == QueueEntry.STATUS_CANCELLED:
        called_at = None
    entry = QueueEntry(
        location_id=location_id,
        customer_name="Customer",
        status=status,
        checked_in_at=checked_in_at,
        called_at=called_at,
        completed_at=completed_at,
        **kwargs,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def local_time_on(days_ago, hour, minute=0, tz=HOBART):
    day = datetime.now(tz).date() - timedelta(days=days_ago)
    return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(timezone.utc)


def test_all_figures_respect_the_selected_period(app, locations, barber):
    with app.app_context():
        add_entry(locations["launceston"], local_time_on(3, 10), called_by_barber_id=barber["id"])
        add_entry(locations["launceston"], local_time_on(20, 10), called_by_barber_id=barber["id"])
        add_entry(locations["launceston"], local_time_on(20, 11), status=QueueEntry.STATUS_CANCELLED)

        last_14 = compute_metrics(14, HOBART)
        assert last_14["total_cuts"] == 1
        assert last_14["barber_series"] == [1]
        assert last_14["location_series"] == [1]
        assert last_14["no_show_count"] == 0

        last_30 = compute_metrics(30, HOBART)
        assert last_30["total_cuts"] == 2
        assert last_30["barber_series"] == [2]
        assert last_30["no_show_count"] == 1


def test_days_split_at_local_midnight_not_utc(app, locations, barber):
    with app.app_context():
        # Midnight today in Hobart is still the previous day in UTC.
        checked_in = local_time_on(0, 0, 0)
        entry = add_entry(locations["launceston"], checked_in, wait=10, service=20, called_by_barber_id=barber["id"])
        completed_local = entry.completed_at.astimezone(HOBART)
        if completed_local > datetime.now(HOBART):
            return  # test is running in the first half hour after local midnight

        local_today = datetime.now(HOBART).date().isoformat()
        utc_day = entry.completed_at.astimezone(timezone.utc).date().isoformat()
        assert utc_day != local_today

        hobart = compute_metrics(7, HOBART)
        assert hobart["day_labels"][-1] == local_today
        assert hobart["cuts_series"][-1] == 1

        utc = compute_metrics(7, ZoneInfo("UTC"))
        assert utc["cuts_series"][utc["day_labels"].index(utc_day)] == 1


def test_heatmap_buckets_check_ins_by_local_weekday_and_hour(app, locations):
    with app.app_context():
        # Most recent past Saturday, 10:15 local time.
        today = datetime.now(HOBART).date()
        days_ago = (today.weekday() - 5) % 7 or 7
        add_entry(locations["launceston"], local_time_on(days_ago, 10, 15))
        add_entry(locations["kings-meadows"], local_time_on(days_ago, 14, 5))

        data = compute_metrics(14, HOBART)
        assert data["heatmap_hours"][0] == "10am"
        assert data["heatmap_hours"][-1] == "2pm"
        assert [view["slug"] for view in data["heatmap_views"]] == ["all", "kings-meadows", "launceston"]

        def cell(view_slug, day, hour_label):
            view = next(v for v in data["heatmap_views"] if v["slug"] == view_slug)
            row = next(r for r in view["rows"] if r["day"] == day)
            return row["cells"][data["heatmap_hours"].index(hour_label)]

        # 14-day window has two Saturdays, so 1 check-in averages 0.5 per Saturday.
        assert cell("all", "Sat", "10am")["total"] == 1
        assert cell("all", "Sat", "10am")["avg"] == 0.5
        assert cell("all", "Sat", "10am")["step"] == 5
        assert cell("all", "Sat", "2pm")["total"] == 1
        assert cell("launceston", "Sat", "10am")["total"] == 1
        assert cell("launceston", "Sat", "2pm")["total"] == 0
        assert cell("launceston", "Sat", "2pm")["step"] == 0
        assert cell("all", "Sun", "10am")["total"] == 0


def test_preferred_barber_demand(app, locations, barber, other_location_barber):
    with app.app_context():
        alex, sam = barber["id"], other_location_barber["id"]
        # Two customers ask for Alex: one gets Alex (30 min wait), one gets Sam (10 min wait).
        add_entry(locations["launceston"], local_time_on(1, 10), wait=30, preferred_barber_id=alex, called_by_barber_id=alex)
        add_entry(locations["launceston"], local_time_on(1, 11), wait=10, preferred_barber_id=alex, called_by_barber_id=sam)
        # Two customers happy with anyone, 5 min waits.
        add_entry(locations["launceston"], local_time_on(1, 12), wait=5, called_by_barber_id=sam)
        add_entry(locations["launceston"], local_time_on(1, 13), wait=5, called_by_barber_id=sam)

        data = compute_metrics(14, HOBART)
        assert data["requested_pct"] == 50
        assert data["avg_wait_requested"] == 20.0
        assert data["avg_wait_anyone"] == 5.0
        assert data["preferred_rows"] == [
            {"barber": "Alex", "requests": 2, "share_pct": 100, "served_pct": 50, "avg_wait_minutes": 20.0}
        ]


def test_service_time_per_barber(app, locations, barber, other_location_barber):
    with app.app_context():
        add_entry(locations["launceston"], local_time_on(1, 10), service=20, called_by_barber_id=barber["id"])
        add_entry(locations["launceston"], local_time_on(1, 11), service=30, called_by_barber_id=barber["id"])
        add_entry(locations["launceston"], local_time_on(1, 12), service=15, called_by_barber_id=other_location_barber["id"])

        data = compute_metrics(14, HOBART)
        assert data["service_rows"] == [
            {"barber": "Alex", "avg_minutes": 25.0, "cuts": 2},
            {"barber": "Sam", "avg_minutes": 15.0, "cuts": 1},
        ]


def test_metrics_page_renders_new_sections(app, client, admin_barber, barber, locations):
    with app.app_context():
        add_entry(locations["launceston"], local_time_on(1, 10), preferred_barber_id=barber["id"], called_by_barber_id=barber["id"])

    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics")
    assert resp.status_code == 200
    assert b"Busiest times" in resp.data
    assert b"All locations" in resp.data
    assert b"Time in chair by barber" in resp.data
    assert b"Preferred barber demand" in resp.data
    assert b"Australia/Hobart" in resp.data


def test_timezone_defaults_to_hobart(app):
    with app.app_context():
        assert get_timezone_name() == DEFAULT_TIMEZONE == "Australia/Hobart"


def test_admin_can_change_timezone(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post("/admin/settings", data={"timezone": "Australia/Perth"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Timezone set to Australia/Perth" in resp.data
    with app.app_context():
        assert get_timezone_name() == "Australia/Perth"

    resp = client.get("/admin/metrics")
    assert b"Australia/Perth" in resp.data


def test_invalid_timezone_is_rejected(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post("/admin/settings", data={"timezone": "Mars/Olympus_Mons"}, follow_redirects=True)
    assert b"Choose a timezone from the list" in resp.data
    with app.app_context():
        assert get_timezone_name() == DEFAULT_TIMEZONE


def test_settings_require_admin(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.post("/admin/settings", data={"timezone": "Australia/Perth"})
    assert resp.status_code == 403


def _csv_rows(resp):
    import csv
    import io

    text = resp.data.decode("utf-8")
    assert text.startswith("﻿")
    return list(csv.reader(io.StringIO(text[1:])))


def test_visits_export_requires_admin(client, barber):
    login(client, barber["username"], barber["password"])
    assert client.get("/admin/metrics/visits.csv").status_code == 403


def test_visits_export_lists_each_check_in_in_the_period(app, client, admin_barber, barber, locations):
    with app.app_context():
        add_entry(
            locations["launceston"],
            local_time_on(2, 10, 15),
            wait=12,
            service=25,
            called_by_barber_id=barber["id"],
            preferred_barber_id=barber["id"],
        )
        add_entry(locations["kings-meadows"], local_time_on(1, 14), status=QueueEntry.STATUS_CANCELLED)
        add_entry(locations["launceston"], local_time_on(10, 10))  # outside a 7-day export

    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics/visits.csv?days=7")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment;" in resp.headers["Content-Disposition"]
    assert "barber-on-george-visits-" in resp.headers["Content-Disposition"]

    header, *rows = _csv_rows(resp)
    assert header[:3] == ["Date", "Location", "Customer"]
    assert len(rows) == 2

    done, cancelled = rows
    expected_date = (datetime.now(HOBART).date() - timedelta(days=2)).isoformat()
    assert done == [
        expected_date, "Launceston", "Customer", "Alex", "Alex", "Done",
        "10:15", "10:27", "10:52", "12", "25",
    ]
    assert cancelled[1] == "Kings Meadows"
    assert cancelled[5] == "No-show / removed"
    assert cancelled[7:] == ["", "", "", ""]


def test_visits_export_neutralises_spreadsheet_formulas(app, client, admin_barber, locations):
    with app.app_context():
        entry = add_entry(locations["launceston"], local_time_on(0, 9), status=QueueEntry.STATUS_WAITING)
        entry.customer_name = '=HYPERLINK("http://evil.example","Click")'
        db.session.commit()

    login(client, admin_barber["username"], admin_barber["password"])
    _, row = _csv_rows(client.get("/admin/metrics/visits.csv"))

    assert row[2] == "'=HYPERLINK(\"http://evil.example\",\"Click\")"


def test_metrics_page_links_to_export_for_selected_period(client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics?days=30")

    assert b"/admin/metrics/visits.csv?days=30" in resp.data
    assert b"Print / Save as PDF" in resp.data
