import csv
import io
import math
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app.authz import admin_required
from app.models import Location, QueueEntry
from app.settings import get_timezone

metrics_bp = Blueprint("metrics", __name__, url_prefix="/admin")

DAY_RANGE_CHOICES = (7, 14, 30, 90)
DEFAULT_DAYS = 14

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
HEATMAP_STEPS = 5


def _as_utc(dt):
    """Queue timestamps are stored timezone-aware (UTC) on Postgres, but SQLite
    (used in tests) drops tzinfo on read - normalize both to aware UTC so
    subtraction, comparisons and local-time conversion always line up."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _minutes_between(start, end):
    return (_as_utc(end) - _as_utc(start)).total_seconds() / 60


def _avg(values):
    return round(sum(values) / len(values), 1) if values else None


def _hour_label(hour):
    suffix = "am" if hour < 12 else "pm"
    return f"{hour % 12 or 12}{suffix}"


def _barber_key(barber):
    return (barber.id, barber.name) if barber else (None, "Unassigned")


def _heatmap(entries, tz, weekday_counts, hours):
    """Average check-ins per weekday/hour slot (local time), bucketed into
    HEATMAP_STEPS shades relative to this view's busiest slot."""
    counts = defaultdict(int)
    for entry in entries:
        local = _as_utc(entry.checked_in_at).astimezone(tz)
        counts[(local.weekday(), local.hour)] += 1

    averages = {
        slot: count / weekday_counts[slot[0]] for slot, count in counts.items() if weekday_counts[slot[0]]
    }
    peak = max(averages.values(), default=0)

    rows = []
    for weekday, day_name in enumerate(WEEKDAY_NAMES):
        cells = []
        for hour in hours:
            avg = averages.get((weekday, hour), 0)
            step = math.ceil(avg / peak * HEATMAP_STEPS) if avg else 0
            cells.append(
                {
                    "avg": round(avg, 1),
                    "total": counts.get((weekday, hour), 0),
                    "step": step,
                    "label": f"{day_name} {_hour_label(hour)}-{_hour_label((hour + 1) % 24)}",
                }
            )
        rows.append({"day": day_name, "cells": cells})
    return {"rows": rows, "peak": round(peak, 1), "total": len(entries)}


def _period(days, tz):
    """(first local day, last local day, UTC start) for the last `days` days including today."""
    today = datetime.now(tz).date()
    first_day = today - timedelta(days=days - 1)
    return first_day, today, datetime.combine(first_day, time.min, tzinfo=tz).astimezone(timezone.utc)


def _selected_days():
    days = request.args.get("days", DEFAULT_DAYS, type=int)
    return days if days in DAY_RANGE_CHOICES else DEFAULT_DAYS


def compute_metrics(days, tz):
    first_day, _, window_start = _period(days, tz)

    # Cuts count toward the day they were finished; everything about the
    # customer's visit (waits, no-shows, busy times, requests) toward the day
    # they checked in.
    done_entries = QueueEntry.query.filter(
        QueueEntry.status == QueueEntry.STATUS_DONE, QueueEntry.completed_at >= window_start
    ).all()
    checked_in_entries = QueueEntry.query.filter(QueueEntry.checked_in_at >= window_start).all()

    # --- Cuts per day / barber / location ---
    day_labels = [(first_day + timedelta(days=i)).isoformat() for i in range(days)]
    cuts_by_day = defaultdict(int)
    cuts_by_barber = defaultdict(int)
    cuts_by_location = defaultdict(int)
    service_by_barber = defaultdict(list)
    service_minutes = []
    for entry in done_entries:
        cuts_by_day[_as_utc(entry.completed_at).astimezone(tz).date().isoformat()] += 1
        cuts_by_barber[_barber_key(entry.called_by)] += 1
        cuts_by_location[entry.location.name] += 1
        if entry.called_at:
            minutes = _minutes_between(entry.called_at, entry.completed_at)
            service_minutes.append(minutes)
            service_by_barber[_barber_key(entry.called_by)].append(minutes)

    barber_pairs = sorted(cuts_by_barber.items(), key=lambda pair: pair[1], reverse=True)
    location_pairs = sorted(cuts_by_location.items(), key=lambda pair: pair[1], reverse=True)

    service_rows = sorted(
        (
            {"barber": key[1], "avg_minutes": _avg(minutes), "cuts": len(minutes)}
            for key, minutes in service_by_barber.items()
        ),
        key=lambda row: row["avg_minutes"],
        reverse=True,
    )

    # --- Waits and no-shows ---
    wait_minutes = [
        _minutes_between(e.checked_in_at, e.called_at) for e in checked_in_entries if e.called_at
    ]
    no_show_count = sum(1 for e in checked_in_entries if e.status == QueueEntry.STATUS_CANCELLED)

    # --- Preferred barber demand ---
    requested = [e for e in checked_in_entries if e.preferred_barber_id is not None]
    anyone = [e for e in checked_in_entries if e.preferred_barber_id is None]
    by_preferred = defaultdict(list)
    for entry in requested:
        by_preferred[_barber_key(entry.preferred_barber)].append(entry)

    preferred_rows = []
    for (barber_id, name), entries in by_preferred.items():
        called = [e for e in entries if e.called_at]
        served_by_them = [e for e in called if e.called_by_barber_id == barber_id]
        preferred_rows.append(
            {
                "barber": name,
                "requests": len(entries),
                "share_pct": round(len(entries) / len(requested) * 100),
                "served_pct": round(len(served_by_them) / len(called) * 100) if called else None,
                "avg_wait_minutes": _avg([_minutes_between(e.checked_in_at, e.called_at) for e in called]),
            }
        )
    preferred_rows.sort(key=lambda row: row["requests"], reverse=True)

    # --- Busiest times heatmap (local time) ---
    weekday_counts = defaultdict(int)
    for i in range(days):
        weekday_counts[(first_day + timedelta(days=i)).weekday()] += 1

    local_hours = [_as_utc(e.checked_in_at).astimezone(tz).hour for e in checked_in_entries]
    heatmap_hours = list(range(min(local_hours), max(local_hours) + 1)) if local_hours else []
    heatmap_views = []
    if checked_in_entries:
        heatmap_views.append(
            {
                "slug": "all",
                "name": "All locations",
                **_heatmap(checked_in_entries, tz, weekday_counts, heatmap_hours),
            }
        )
        by_location = defaultdict(list)
        for entry in checked_in_entries:
            by_location[entry.location_id].append(entry)
        for location in Location.query.filter(Location.id.in_(by_location)).order_by(Location.name):
            heatmap_views.append(
                {
                    "slug": location.slug,
                    "name": location.name,
                    **_heatmap(by_location[location.id], tz, weekday_counts, heatmap_hours),
                }
            )

    return {
        "total_cuts": len(done_entries),
        "avg_wait_minutes": _avg(wait_minutes),
        "avg_service_minutes": _avg(service_minutes),
        "no_show_count": no_show_count,
        "check_in_count": len(checked_in_entries),
        "requested_pct": round(len(requested) / len(checked_in_entries) * 100) if checked_in_entries else None,
        "avg_wait_requested": _avg(
            [_minutes_between(e.checked_in_at, e.called_at) for e in requested if e.called_at]
        ),
        "avg_wait_anyone": _avg([_minutes_between(e.checked_in_at, e.called_at) for e in anyone if e.called_at]),
        "preferred_rows": preferred_rows,
        "service_rows": service_rows,
        "day_labels": day_labels,
        "cuts_series": [cuts_by_day.get(day, 0) for day in day_labels],
        "barber_labels": [key[1] for key, _ in barber_pairs],
        "barber_series": [count for _, count in barber_pairs],
        "location_labels": [name for name, _ in location_pairs],
        "location_series": [count for _, count in location_pairs],
        "heatmap_hours": [_hour_label(hour) for hour in heatmap_hours],
        "heatmap_views": heatmap_views,
        "heatmap_steps": HEATMAP_STEPS,
    }


@metrics_bp.route("/metrics")
@login_required
@admin_required
def metrics():
    days = _selected_days()
    tz = get_timezone()
    data = compute_metrics(days, tz)
    first_day, last_day, _ = _period(days, tz)

    return render_template(
        "admin/metrics.html",
        days=days,
        day_range_choices=DAY_RANGE_CHOICES,
        timezone_name=tz.key,
        period_start=f"{first_day.day} {first_day:%b %Y}",
        period_end=f"{last_day.day} {last_day:%b %Y}",
        **data,
    )


EXPORT_STATUS_LABELS = {
    QueueEntry.STATUS_WAITING: "Waiting",
    QueueEntry.STATUS_IN_PROGRESS: "In chair",
    QueueEntry.STATUS_DONE: "Done",
    QueueEntry.STATUS_CANCELLED: "No-show / removed",
}


def _csv_safe(value):
    """Customer names are typed by the public on the kiosk, so stop spreadsheet
    apps treating a value like '=HYPERLINK(...)' as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def visits_csv(days, tz):
    """One row per check-in in the period (by check-in time), times in shop-local time."""
    _, _, window_start = _period(days, tz)
    entries = (
        QueueEntry.query.filter(QueueEntry.checked_in_at >= window_start)
        .order_by(QueueEntry.checked_in_at.asc())
        .all()
    )

    def local(dt):
        return _as_utc(dt).astimezone(tz) if dt else None

    def clock(dt):
        return local(dt).strftime("%H:%M") if dt else ""

    buffer = io.StringIO()
    # Byte-order mark so Excel opens it as UTF-8 (names with accents etc.).
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Date",
            "Location",
            "Customer",
            "Preferred barber",
            "Served by",
            "Status",
            "Checked in",
            "Called",
            "Finished",
            "Wait (min)",
            "Time in chair (min)",
        ]
    )
    for entry in entries:
        wait = round(_minutes_between(entry.checked_in_at, entry.called_at)) if entry.called_at else ""
        service = (
            round(_minutes_between(entry.called_at, entry.completed_at))
            if entry.called_at and entry.completed_at
            else ""
        )
        writer.writerow(
            [
                local(entry.checked_in_at).date().isoformat(),
                entry.location.name,
                _csv_safe(entry.customer_name),
                _csv_safe(entry.preferred_barber.name) if entry.preferred_barber else "",
                _csv_safe(entry.called_by.name) if entry.called_by else "",
                EXPORT_STATUS_LABELS.get(entry.status, entry.status),
                clock(entry.checked_in_at),
                clock(entry.called_at),
                clock(entry.completed_at),
                wait,
                service,
            ]
        )
    return buffer.getvalue()


@metrics_bp.route("/metrics/visits.csv")
@login_required
@admin_required
def export_visits():
    days = _selected_days()
    tz = get_timezone()
    first_day, last_day, _ = _period(days, tz)
    filename = f"barber-on-george-visits-{first_day.isoformat()}-to-{last_day.isoformat()}.csv"
    return Response(
        visits_csv(days, tz),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
