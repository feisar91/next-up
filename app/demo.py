"""Demo data for trying the app out and for the documentation screenshots
(`flask seed-demo`, docs/tools/capture.py): a made-up two-location shop with
barbers, opening hours, a month of past visits and a live queue for today.

Only runs on an empty database, so it can never mix made-up customers into a
real shop's history.
"""
import random
from datetime import datetime, time, timedelta, timezone

from app import branding, db
from app.models import (
    AdminAction,
    Barber,
    Location,
    OpeningHours,
    QueueEntry,
    Setting,
    SpecialHours,
)
from app.settings import get_timezone, get_timezone_name, set_timezone_name

SHOP_NAME = "Harbour Lane Barbers"
LOCATIONS = [
    {"name": "Harbour Lane", "slug": "harbour-lane", "address": "41 Harbour Lane"},
    {"name": "Station Street", "slug": "station-street", "address": "7 Station Street"},
]
# (name, username, location index or None, admin)
BARBERS = [
    ("Dana Wells", "dana", 0, True),
    ("Marco", "marco", 0, False),
    ("Priya", "priya", 0, False),
    ("Tom", "tom", 0, False),
    ("Jess", "jess", 1, False),
    ("Leo", "leo", 1, False),
]
ON_DUTY = {"marco": 0, "priya": 0, "tom": 0, "jess": 1, "leo": 1}

# weekday -> (opens, closes); Sunday closed.
WEEKLY_HOURS = {
    0: (time(9), time(17, 30)),
    1: (time(9), time(17, 30)),
    2: (time(9), time(17, 30)),
    3: (time(9), time(19)),
    4: (time(9), time(17, 30)),
    5: (time(8, 30), time(15)),
}
# Rough check-ins per day at the main shop; the second shop gets about 60%.
DAILY_VISITS = {0: 16, 1: 18, 2: 20, 3: 28, 4: 32, 5: 42}
HISTORY_DAYS = 35

FIRST_NAMES = [
    "Aaron", "Ben", "Callum", "Daniel", "Eli", "Finn", "George", "Harry", "Isaac", "Jack",
    "Kai", "Liam", "Mason", "Noah", "Oscar", "Patrick", "Quinn", "Ryan", "Sam", "Theo",
    "Umar", "Vince", "Will", "Xavier", "Yusuf", "Zac", "Adam", "Chris", "Dylan", "Ethan",
    "Hugo", "Jordan", "Luke", "Max", "Nathan", "Owen", "Riley", "Sean", "Toby", "Zane",
]
LAST_NAMES = [
    "Smith", "Nguyen", "Brown", "Wilson", "Taylor", "Martin", "Clarke", "Walker", "Patel", "Hughes",
    "Kelly", "Murphy", "Evans", "Roberts", "Turner", "Lee", "King", "Wright", "Hall", "Baker",
]

# The live queue for today at the main shop, as (name, minutes ago, preferred barber).
WAITING_NOW = [
    ("Jordan Smith", 24, None),
    ("Ethan Clarke", 17, "priya"),
    ("Kai Walker", 11, None),
    ("Mason Lee", 6, None),
    ("Oscar Lee", 6, None),  # checked in with Mason (a group)
    ("Ryan Patel", 2, "priya"),
]
IN_CHAIR_NOW = [("Liam Hughes", 14, "marco"), ("Noah Turner", 6, "tom")]
ANNOUNCEMENT = "Closing at 4 pm on Friday for a staff training night"


class DemoError(Exception):
    pass


def seed_demo(password, rng=None):
    if Barber.query.first() or Location.query.first():
        raise DemoError("The demo data only goes into an empty database, and this one already has logins or locations.")
    rng = rng or random.Random(7)
    tz = get_timezone()
    now = datetime.now(timezone.utc)

    branding.update_identity(SHOP_NAME, branding.DEFAULT_DARK, branding.DEFAULT_ACCENT)
    set_timezone_name(get_timezone_name())

    locations = [Location(**fields) for fields in LOCATIONS]
    db.session.add_all(locations)
    db.session.flush()
    for location in locations:
        location.auto_hours = location is locations[1]
        location.checkin_cutoff_minutes = 15
        for weekday, (opens, closes) in WEEKLY_HOURS.items():
            db.session.add(OpeningHours(location=location, weekday=weekday, opens_at=opens, closes_at=closes))
        today = now.astimezone(tz).date()
        db.session.add(SpecialHours(location=location, date=today + timedelta(days=9), note="Staff training day"))
        db.session.add(
            SpecialHours(
                location=location, date=today + timedelta(days=16), opens_at=time(9), closes_at=time(13), note="Half day"
            )
        )
        # As if the kiosk and TV have been set up already.
        location.kiosk_last_seen_at = location.display_last_seen_at = now - timedelta(minutes=1)

    barbers = {}
    for name, username, location_index, is_admin in BARBERS:
        barber = Barber(
            name=name,
            username=username,
            is_admin=is_admin,
            show_on_kiosk=not is_admin,
            default_location_id=locations[location_index].id if location_index is not None else None,
        )
        barber.set_password(password)
        if username in ON_DUTY:
            barber.on_duty_location_id = locations[ON_DUTY[username]].id
            barber.on_duty_since = now - timedelta(hours=3)
        db.session.add(barber)
        barbers[username] = barber
    db.session.flush()

    _history(locations, barbers, tz, now, rng)
    _today(locations, barbers, now, rng)

    locations[0].announcement = ANNOUNCEMENT
    midnight = datetime.combine(now.astimezone(tz).date() + timedelta(days=1), time.min, tzinfo=tz)
    locations[0].announcement_until = midnight.astimezone(timezone.utc)
    db.session.add(Setting(key="setup_checklist_hidden", value="1"))
    db.session.commit()
    return {"locations": len(locations), "barbers": len(barbers), "visits": QueueEntry.query.count()}


def _random_name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _local(day, minutes, tz):
    return (datetime.combine(day, time.min, tzinfo=tz) + timedelta(minutes=minutes)).astimezone(timezone.utc)


def _history(locations, barbers, tz, now, rng):
    """Finished visits for the past few weeks, busiest at lunch, after work and on Saturdays."""
    staff = {
        0: [barbers["marco"], barbers["priya"], barbers["tom"]],
        1: [barbers["jess"], barbers["leo"]],
    }
    today = now.astimezone(tz).date()
    for days_ago in range(HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=days_ago)
        hours = WEEKLY_HOURS.get(day.weekday())
        if not hours:
            continue
        opens = hours[0].hour * 60 + hours[0].minute
        closes = hours[1].hour * 60 + hours[1].minute - 30
        for index, location in enumerate(locations):
            expected = DAILY_VISITS[day.weekday()] * (1 if index == 0 else 0.6)
            for _ in range(max(0, round(rng.gauss(expected, expected * 0.15)))):
                # Two peaks: around 12:30 and around 4:30 pm, plus a steady trickle.
                peak = rng.choice([750, 990, rng.uniform(opens, closes)])
                minute = min(max(rng.gauss(peak, 50), opens), closes)
                checked_in = _local(day, minute, tz)
                preferred = rng.choice(staff[index]) if rng.random() < 0.35 else None
                entry = QueueEntry(location_id=location.id, customer_name=_random_name(rng),
                                   preferred_barber_id=preferred.id if preferred else None, checked_in_at=checked_in)
                wait = timedelta(minutes=max(2, rng.gauss(22 if day.weekday() == 5 else 13, 7)))
                if rng.random() < 0.07:
                    entry.status = QueueEntry.STATUS_CANCELLED
                    entry.removed_at = checked_in + wait
                else:
                    barber = preferred or rng.choice(staff[index])
                    entry.status = QueueEntry.STATUS_DONE
                    entry.called_at = checked_in + wait
                    entry.called_by_barber_id = barber.id
                    entry.completed_at = entry.called_at + timedelta(minutes=max(12, rng.gauss(26, 6)))
                db.session.add(entry)


def _log(when, actor, action, summary, category):
    db.session.add(
        AdminAction(created_at=when, actor_id=actor.id if actor else None,
                    actor_name=actor.name if actor else "Customer", action=action, summary=summary, category=category)
    )


def _today(locations, barbers, now, rng):
    """Today's queue at both shops, plus matching Activity entries."""
    main, second = locations
    for username in ON_DUTY:
        barber = barbers[username]
        location = locations[ON_DUTY[username]]
        when = now - timedelta(hours=3, minutes=rng.randint(0, 20))
        _log(when, barber, "session.login", f"{barber.name} logged in", "barber")
        _log(when + timedelta(seconds=20), barber, "session.location",
             f"{barber.name} started working at {location.name}", "barber")

    def add(location, name, minutes_ago, preferred=None, status=QueueEntry.STATUS_WAITING, called_by=None,
            chair_minutes=None, finished_minutes_ago=None):
        checked_in = now - timedelta(minutes=minutes_ago)
        entry = QueueEntry(location_id=location.id, customer_name=name, checked_in_at=checked_in, status=status,
                           preferred_barber_id=barbers[preferred].id if preferred else None)
        detail = f" (prefers {barbers[preferred].name})" if preferred else ""
        _log(checked_in, None, "queue.checkin", f"{name} checked in at {location.name}{detail}", "customer")
        if called_by:
            barber = barbers[called_by]
            entry.called_by_barber_id = barber.id
            entry.called_at = now - timedelta(minutes=chair_minutes)
            _log(entry.called_at, barber, "queue.call", f"Called {name} to the chair at {location.name}", "barber")
        if status == QueueEntry.STATUS_DONE:
            entry.completed_at = now - timedelta(minutes=finished_minutes_ago)
            _log(entry.completed_at, barbers[called_by], "queue.complete", f"Completed {name} at {location.name}", "barber")
        if status == QueueEntry.STATUS_CANCELLED:
            entry.removed_at = now - timedelta(minutes=finished_minutes_ago)
            _log(entry.removed_at, barbers["priya"], "queue.remove",
                 f"Removed {name} from the queue at {location.name} (no-show)", "barber")
        db.session.add(entry)

    # Earlier today at the main shop.
    for i, (barber, name) in enumerate([("marco", "Hugo Martin"), ("tom", "Owen King"), ("priya", "Toby Hall"),
                                        ("marco", "Sean Baker"), ("tom", "Will Evans")]):
        start = 150 - i * 25
        add(main, name, start, status=QueueEntry.STATUS_DONE, called_by=barber,
            chair_minutes=start - 10, finished_minutes_ago=start - 36)
    add(main, "Adam Wright", 40, status=QueueEntry.STATUS_DONE, called_by="priya", chair_minutes=30, finished_minutes_ago=4)
    add(main, "Zac Kelly", 35, status=QueueEntry.STATUS_CANCELLED, finished_minutes_ago=7)
    for name, minutes_ago, barber in IN_CHAIR_NOW:
        add(main, name, minutes_ago + 12, status=QueueEntry.STATUS_IN_PROGRESS, called_by=barber, chair_minutes=minutes_ago)
    for name, minutes_ago, preferred in WAITING_NOW:
        add(main, name, minutes_ago, preferred)

    add(second, "Callum Roberts", 20, status=QueueEntry.STATUS_IN_PROGRESS, called_by="jess", chair_minutes=8)
    add(second, "Finn Murphy", 9)
    add(second, "Isaac Nguyen", 3, "leo")
