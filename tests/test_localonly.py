"""Only requests for this computer are answered, and changes only when they come from the analyser's own page (alex/localonly.py)."""
from __future__ import annotations

HOST = "127.0.0.1:8766"
CHANGE = ("/api/settings", {"conv_gap": 30})        # a request that changes something


def change(client, **headers):
    """Make the change request with the given headers (the Host is the analyser's own unless given)."""
    headers.setdefault("host", HOST)
    return client.post(CHANGE[0], json=CHANGE[1], headers=headers)


def conv_gap(client):
    """The conversation gap now in the settings."""
    return client.get("/api/library", headers={"host": HOST}).json()["settings"]["conv_gap"]


def test_the_page_and_the_data_are_served_to_127_0_0_1_and_localhost_with_or_without_a_port(client):
    for host in ("127.0.0.1", "127.0.0.1:8766", "localhost", "localhost:8766"):
        assert client.get("/", headers={"host": host}).status_code == 200, host
        assert client.get("/api/library", headers={"host": host}).status_code == 200, host


def test_another_name_for_this_computer_is_refused_whatever_the_method(client):
    """DNS rebinding: a page on evil.example made to resolve to 127.0.0.1 still sends its own name in Host."""
    for host in ("evil.example", "evil.example:8766", "127.0.0.1.evil.example", "127.0.0.1:8766@evil.example", "127.0.0.1:abc", "[::1]:8766", ""):
        assert client.get("/api/library", headers={"host": host}).status_code == 403, host
        assert client.post(CHANGE[0], json=CHANGE[1], headers={"host": host}).status_code == 403, host
    assert "127.0.0.1 or localhost" in client.get("/", headers={"host": "evil.example"}).json()["detail"]


def test_a_change_asked_for_by_another_web_page_is_refused_and_does_nothing(client):
    before = conv_gap(client)
    for origin in ("https://evil.example", "http://evil.example", "null", "http://localhost:8765",         # another site, a sandboxed page, another program here
                   "http://127.0.0.1:9999", "https://127.0.0.1:8766", "http://localhost:8766"):             # another port, https, another spelling of our host
        r = change(client, origin=origin)
        assert r.status_code == 403 and "another web page" in r.json()["detail"], origin
    assert conv_gap(client) == before


def test_a_change_from_our_own_page_or_from_a_script_goes_through(client):
    assert change(client, origin=f"http://{HOST}").status_code == 200                # the browser's own page: Origin is the server itself
    assert conv_gap(client) == 30
    CHANGE[1]["conv_gap"] = 31
    try:
        assert change(client).status_code == 200                                   # no Origin: curl or a script, not a web page
    finally:
        CHANGE[1]["conv_gap"] = 30
    assert conv_gap(client) == 31


def test_reading_is_not_refused_for_its_origin(client):
    """Reading changes nothing, and without permission headers a foreign page can't read the answer anyway."""
    r = client.get("/api/library", headers={"host": HOST, "origin": "https://evil.example"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
