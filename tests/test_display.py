from tests.conftest import display_url


def test_display_page_includes_a_hidden_connection_lost_banner(app, client, locations):
    resp = client.get(display_url(app, "launceston"))
    assert resp.status_code == 200
    assert b'id="connection-banner"' in resp.data
    assert b"Connection lost" in resp.data
