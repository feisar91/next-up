from app import db
from app.kiosk import MAX_GROUP_SIZE
from app.models import Location, QueueEntry
from app.sockets import queue_state
from tests.conftest import kiosk_url, login


def test_checkin_adds_waiting_entry(app, client, locations):
    resp = client.post(
        kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""}
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == kiosk_url(app, "launceston")

    with app.app_context():
        entries = QueueEntry.query.all()
        assert len(entries) == 1
        assert entries[0].customer_name == "Jamie"
        assert entries[0].status == QueueEntry.STATUS_WAITING


def test_checkin_confirmation_is_shown_once_and_reloading_it_adds_nobody(app, client, locations):
    url = kiosk_url(app, "launceston")
    resp = client.post(url, data={"customer_name": "Jamie", "preferred_barber_id": ""}, follow_redirects=True)
    assert b"You're checked in, Jamie" in resp.data

    # A reload (deploy, store opening/closing) is a plain GET: back to the form, no new entry.
    resp = client.get(url)
    assert b"You're checked in" not in resp.data
    assert b'name="customer_name"' in resp.data
    with app.app_context():
        assert QueueEntry.query.count() == 1


def test_checkin_to_a_closed_store_redirects_without_adding_anyone(app, client, locations):
    with app.app_context():
        Location.query.filter_by(slug="launceston").one().closed = True
        db.session.commit()

    resp = client.post(
        kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""}, follow_redirects=True
    )
    assert b"We're closed right now" in resp.data
    with app.app_context():
        assert QueueEntry.query.count() == 0


def test_checkin_requires_name(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "", "preferred_barber_id": ""})

    with app.app_context():
        assert QueueEntry.query.count() == 0


def test_group_checkin_adds_everyone_in_consecutive_places(app, client, locations, barber):
    staff = app.test_client()
    login(staff, barber["username"], barber["password"])
    staff.get("/staff/launceston")  # on duty, so the kiosk offers Alex
    url = kiosk_url(app, "launceston")
    client.post(url, data={"customer_name": "Already Waiting", "preferred_barber_id": ""})

    resp = client.post(
        url,
        data={"customer_name": ["Dana", " ", "Mia", "Leo"], "preferred_barber_id": barber["id"]},
        follow_redirects=True,
    )

    html = resp.data.decode()
    assert "You're all checked in at Launceston" in html
    rows = [f'"group-position">#{n}</span><span class="group-name">{name}<' for n, name in [(2, "Dana"), (3, "Mia"), (4, "Leo")]]
    assert all(row in html for row in rows)
    assert html.index(rows[0]) < html.index(rows[1]) < html.index(rows[2])
    with app.app_context():
        waiting = queue_state(db.session.get(Location, locations["launceston"]))["waiting"]
        assert [e["customer_name"] for e in waiting] == ["Already Waiting", "Dana", "Mia", "Leo"]
        # The group shares the preferred barber and one check-in time.
        group = QueueEntry.query.filter(QueueEntry.customer_name.in_(["Dana", "Mia", "Leo"])).all()
        assert {e.preferred_barber_id for e in group} == {barber["id"]}
        assert len({e.checked_in_at for e in group}) == 1


def test_group_checkin_stays_together_ahead_of_later_customers(app, client, locations):
    url = kiosk_url(app, "launceston")
    client.post(url, data={"customer_name": ["Dana", "Mia"], "preferred_barber_id": ""})
    client.post(url, data={"customer_name": "Later", "preferred_barber_id": ""})

    with app.app_context():
        waiting = queue_state(db.session.get(Location, locations["launceston"]))["waiting"]
        assert [e["customer_name"] for e in waiting] == ["Dana", "Mia", "Later"]


def test_group_checkin_is_capped(app, client, locations):
    names = [f"Person {i}" for i in range(MAX_GROUP_SIZE + 3)]
    client.post(kiosk_url(app, "launceston"), data={"customer_name": names, "preferred_barber_id": ""})

    with app.app_context():
        assert QueueEntry.query.count() == MAX_GROUP_SIZE


def test_group_checkin_with_only_blank_names_adds_nobody(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": ["", "  "], "preferred_barber_id": ""})

    with app.app_context():
        assert QueueEntry.query.count() == 0


def test_single_checkin_keeps_the_big_position_number(app, client, locations):
    resp = client.post(
        kiosk_url(app, "launceston"), data={"customer_name": ["Jamie", ""], "preferred_barber_id": ""},
        follow_redirects=True,
    )
    assert b"You're checked in, Jamie" in resp.data
    assert b'<div class="position">#1</div>' in resp.data
    assert b"group-positions" not in resp.data


def test_kiosk_offers_adding_another_person(app, client, locations):
    html = client.get(kiosk_url(app, "launceston")).data.decode()
    assert f'id="add-person" data-max-group-size="{MAX_GROUP_SIZE}"' in html
    template = html[html.index('<template id="group-person-template">'):html.index("</template>")]
    assert 'name="customer_name"' in template
    assert 'autocomplete="off"' in template
    assert 'spellcheck="false"' in template


def test_kiosk_name_field_turns_off_browser_suggestions(app, client, locations):
    html = client.get(kiosk_url(app, "launceston")).data.decode()
    assert '<form class="kiosk-form" method="post" autocomplete="off">' in html
    name_input = html[html.index('id="customer_name"'):]
    name_input = name_input[: name_input.index(">")]
    assert 'autocomplete="off"' in name_input
    assert 'autocorrect="off"' in name_input
    assert 'spellcheck="false"' in name_input


def test_checkin_unknown_location_404s(client):
    resp = client.get("/kiosk/nowhere/some-token")
    assert resp.status_code == 404


def test_checkin_wrong_token_404s(app, client, locations):
    resp = client.get("/kiosk/launceston/wrong-token")
    assert resp.status_code == 404


def test_barber_can_call_and_complete_own_location_customer(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry = QueueEntry.query.filter_by(customer_name="Jamie").first()
        entry_id = entry.id

    resp = client.post(f"/staff/launceston/call/{entry_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_IN_PROGRESS
        assert entry.called_by_barber_id == barber["id"]

    resp = client.post(f"/staff/launceston/complete/{entry_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_DONE


def test_barber_can_remove_waiting_customer(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id

    client.post(f"/staff/launceston/remove/{entry_id}", follow_redirects=True)

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_CANCELLED


def test_dashboard_renders_waiting_customers(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    resp = client.get("/staff/launceston")
    assert resp.status_code == 200
    assert b"Jamie" in resp.data
    assert b"#1" in resp.data


def test_dashboard_renders_customer_in_chair(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id
    client.post(f"/staff/launceston/call/{entry_id}")

    resp = client.get("/staff/launceston")
    assert resp.status_code == 200
    assert b"Jamie" in resp.data
    assert b"Alex" in resp.data  # the barber who called them to the chair


def test_queue_position_ordering(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "First", "preferred_barber_id": ""})
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Second", "preferred_barber_id": ""})

    with app.app_context():
        entries = (
            QueueEntry.query.filter_by(status=QueueEntry.STATUS_WAITING)
            .order_by(QueueEntry.checked_in_at.asc())
            .all()
        )
        assert [e.customer_name for e in entries] == ["First", "Second"]


def test_closed_store_shows_closed_message_and_rejects_checkin(app, client, locations):
    with app.app_context():
        Location.query.filter_by(slug="launceston").update({"closed": True})
        db.session.commit()

    resp = client.get(kiosk_url(app, "launceston"))
    assert resp.status_code == 200
    assert b"closed" in resp.data.lower()

    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    with app.app_context():
        assert QueueEntry.query.count() == 0


def test_barber_can_close_and_reopen_store(app, client, locations, barber):
    login(client, barber["username"], barber["password"])

    resp = client.post("/staff/launceston/store", data={"closed": "1"}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Location.query.filter_by(slug="launceston").first().closed is True

    resp = client.post("/staff/launceston/store", data={"closed": "0"}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Location.query.filter_by(slug="launceston").first().closed is False


def test_closing_store_requires_login(client, locations):
    resp = client.post("/staff/launceston/store", data={"closed": "1"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]



def _waiting(app, location_id, name, preferred_barber_id=None):
    with app.app_context():
        db.session.add(
            QueueEntry(location_id=location_id, customer_name=name, preferred_barber_id=preferred_barber_id)
        )
        db.session.commit()


def test_waiting_customers_who_asked_for_you_are_highlighted(app, client, locations, barber, other_location_barber):
    _waiting(app, locations["launceston"], "Jamie", barber["id"])
    _waiting(app, locations["launceston"], "Robin", other_location_barber["id"])
    _waiting(app, locations["launceston"], "Casey")

    login(client, barber["username"], barber["password"])
    html = client.get("/staff/launceston").data.decode()

    waiting = html[html.index('id="waiting-list"'):]
    rows = {name: waiting[waiting.rindex('<div class="staff-row', 0, waiting.index(name)):waiting.index(name)]
            for name in ("Jamie", "Robin", "Casey")}
    assert "is-mine" in rows["Jamie"]
    assert "is-mine" not in rows["Robin"] and "is-mine" not in rows["Casey"]
    assert "Asked for you" in waiting
    assert "Prefers Sam" in waiting


def test_queue_updates_carry_the_preferred_barber_id(app, locations, barber):
    _waiting(app, locations["launceston"], "Jamie", barber["id"])
    with app.app_context():
        from app.sockets import staff_queue_state

        state = staff_queue_state(Location.query.filter_by(slug="launceston").one())
    assert state["waiting"][0]["preferred_barber_id"] == barber["id"]
