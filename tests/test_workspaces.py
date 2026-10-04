"""Workspaces: the list and the active one, creating, renaming and forgetting, and making one from an export zip."""
from __future__ import annotations

import json
import threading
import zipfile

import pytest

from alex.core import export
from alex.core.library import Library, LibraryError
from alex.core.workspaces import DEFAULT_ID, Workspaces
from test_export import make_work


@pytest.fixture
def ws(tmp_path):
    """A list of workspaces in its own folder, with the Default workspace at tmp/data."""
    return Workspaces(tmp_path / "workspaces.json", default_data=tmp_path / "data")


def make_zip(lib, books, dest):
    """An export zip of `books` at `dest` (with some work in the library, see test_export.make_work)."""
    make_work(lib)
    export.write_zip(lib, books, dest)
    return dest


def rewrite(src, dst, change):
    """Copy a zip, letting `change(name, data) -> data or None` alter or drop members, and add nothing else."""
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst, "w") as b:
        for n in a.namelist():
            data = change(n, a.read(n))
            if data is not None:
                b.writestr(n, data)
    return dst


# ---------- the list ----------
def test_a_fresh_list_has_the_default_workspace_active(ws, tmp_path):
    assert [(w["id"], w["name"], w["active"]) for w in ws.listing()] == [(DEFAULT_ID, "Default", True)]
    assert ws.folder() == tmp_path / "data" and not (tmp_path / "workspaces.json").exists()      # nothing is written until something changes


def test_create_activate_rename_and_forget(ws, tmp_path):
    a = ws.create(" Holmes ", sources=[tmp_path / "somewhere"])
    b = ws.create("Austen")
    assert Library(data_dir=ws.folder(b)).state["sources"] == []                                  # no folder given: none, they are added later
    assert a == "holmes" and ws.get(a)["name"] == "Holmes"
    assert Library(data_dir=ws.folder(a)).state["sources"] == [str(tmp_path / "somewhere")]       # its own folder, its own sources
    assert [w["name"] for w in ws.listing()] == ["Default", "Holmes", "Austen"]
    ws.activate(b)
    assert ws.active == b and ws.folder() == ws.folder(b)
    ws.rename(a, "Sherlock")
    assert ws.get(a)["name"] == "Sherlock"
    with pytest.raises(ValueError):
        ws.forget(b)                                                                              # the one in use stays
    ws.forget(a)
    assert [w["id"] for w in ws.listing()] == [DEFAULT_ID, b]
    assert (tmp_path / "workspaces" / a / "library.json").exists()                                # forgetting keeps the files
    again = ws.create("Holmes")                                                                   # the name is free, the folder is not
    assert again == "holmes-2" and (tmp_path / "workspaces" / a / "library.json").exists()


def test_names_must_be_given_and_unique(ws):
    ws.create("Holmes")
    for bad in ("", "   ", None, "holmes", "Default"):
        with pytest.raises(ValueError):
            ws.create(bad)
    other = ws.create("Austen")
    with pytest.raises(ValueError):
        ws.rename(other, "HOLMES")
    ws.rename(other, "Austen")                                                                    # its own name again is fine


def test_unknown_ids_are_key_errors(ws):
    for action in (ws.get, ws.activate, ws.forget):
        with pytest.raises(KeyError):
            action("nope")
    with pytest.raises(KeyError):
        ws.rename("nope", "x")


def test_the_list_and_the_active_workspace_are_remembered(ws, tmp_path):
    a = ws.create("Holmes")
    ws.activate(a)
    again = Workspaces(tmp_path / "workspaces.json", default_data=tmp_path / "data")
    assert again.active == a and [w["name"] for w in again.listing()] == ["Default", "Holmes"]


def test_a_missing_folder_is_flagged_and_cannot_be_opened(ws, tmp_path):
    a = ws.create("Holmes")
    (tmp_path / "workspaces" / a / "library.json").unlink()
    (tmp_path / "workspaces" / a / "cache").rmdir()
    (tmp_path / "workspaces" / a).rmdir()
    assert next(w for w in ws.listing() if w["id"] == a)["missing"]
    with pytest.raises(ValueError):
        ws.activate(a)
    ws.forget(a)


def test_a_damaged_list_stops_with_a_message_and_is_not_overwritten(tmp_path):
    (tmp_path / "workspaces.json").write_text("{not json")
    with pytest.raises(LibraryError):
        Workspaces(tmp_path / "workspaces.json")
    assert (tmp_path / "workspaces.json").read_text() == "{not json"


def test_a_list_pointing_at_nothing_falls_back_to_default(tmp_path):
    (tmp_path / "workspaces.json").write_text(json.dumps({"active": "gone", "workspaces": {"x": {"name": "X", "path": str(tmp_path)}}}))
    ws = Workspaces(tmp_path / "workspaces.json", default_data=tmp_path / "data")
    assert ws.active == DEFAULT_ID and [w["id"] for w in ws.listing()] == ["x", DEFAULT_ID]       # Default is put back if the file lacks it


def test_the_data_folder_is_alex_data_here_unless_alex_data_says_otherwise(monkeypatch, tmp_path):
    """The Default workspace is the data folder itself, and the list and the other workspaces' folders live in it."""
    from alex.core import workspaces
    from alex.core.library import data_home
    monkeypatch.delenv("ALEX_DATA", raising=False)
    monkeypatch.chdir(tmp_path)
    assert data_home() == (tmp_path / "alex-data").resolve()                                   # the folder you start it from
    monkeypatch.setenv("ALEX_DATA", str(tmp_path / "elsewhere"))
    assert data_home() == tmp_path / "elsewhere"
    assert workspaces.default_registry() == tmp_path / "elsewhere" / "workspaces.json"
    ws = Workspaces()
    assert ws.root == tmp_path / "elsewhere" / "workspaces" and ws.folder() == tmp_path / "elsewhere"


def test_delete_needs_the_typed_name_and_only_removes_what_the_analyser_made(ws, tmp_path):
    mine = ws.create("Holmes")
    pointed = tmp_path / "my-own-folder"
    pointed.mkdir()
    (pointed / "keep.txt").write_text("precious")
    ws.state["workspaces"]["own"] = {"name": "Own", "path": str(pointed)}                          # a folder the analyser did not make
    for wid, typed in ((mine, "holmes"), (mine, ""), (mine, None)):
        with pytest.raises(ValueError):
            ws.delete(wid, typed)                                                                  # the name must match exactly, case included
    assert ws.folder(mine).is_dir()
    with pytest.raises(ValueError):
        ws.delete("own", "Own")
    with pytest.raises(ValueError):
        ws.delete(DEFAULT_ID, "Default")
    assert (pointed / "keep.txt").read_text() == "precious" and ws.folder(DEFAULT_ID) == tmp_path / "data"
    ws.activate(mine)
    with pytest.raises(ValueError):
        ws.delete(mine, "Holmes")                                                                  # not the one in use
    ws.activate(DEFAULT_ID)
    folder = ws.folder(mine)
    ws.delete(mine, "Holmes")
    assert not folder.exists() and mine not in [w["id"] for w in ws.listing()]
    with pytest.raises(KeyError):
        ws.delete(mine, "Holmes")


def test_deleting_a_workspace_whose_folder_is_already_gone_just_removes_it(ws):
    import shutil
    a = ws.create("Holmes")
    shutil.rmtree(ws.folder(a))
    ws.delete(a, "Holmes")
    assert a not in [w["id"] for w in ws.listing()]


def test_a_link_out_of_the_workspaces_folder_is_not_owned(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    a = ws.create("Holmes")
    import shutil
    shutil.rmtree(ws.folder(a))
    ws.folder(a).symlink_to(outside)                                                               # a workspace folder replaced by a link elsewhere
    with pytest.raises(ValueError):
        ws.delete(a, "Holmes")
    assert outside.is_dir()


def test_default_cannot_be_removed_from_the_list_and_can_always_be_opened(ws, tmp_path):
    with pytest.raises(ValueError):
        ws.forget(DEFAULT_ID)
    assert not (tmp_path / "data").exists()
    assert ws.openable(DEFAULT_ID) == tmp_path / "data" and not ws.listing()[0]["missing"]       # opening it makes the folder


def test_listing_says_which_workspaces_can_be_deleted(ws, tmp_path):
    ws.create("Holmes")
    ws.state["workspaces"]["own"] = {"name": "Own", "path": str(tmp_path)}
    assert {w["id"]: w["owned"] for w in ws.listing()} == {DEFAULT_ID: False, "holmes": True, "own": False}


def test_a_workspace_is_found_by_id_or_name(ws):
    ws.create("Jane Austen")
    assert ws.find("jane-austen") == ws.find(" JANE austen ") == "jane-austen" and ws.find("default") == ws.find("Default") == DEFAULT_ID
    with pytest.raises(ValueError, match="Jane Austen"):                                          # the message lists what there is
        ws.find("nope")


# ---------- importing ----------
def test_an_export_becomes_a_workspace_with_its_own_books_and_state(lib, ws, tmp_path):
    zip_path = make_zip(lib, ["alpha", "beta"], tmp_path / "out.zip")
    wid = ws.import_zip(zip_path, name="Shared")
    folder = ws.folder(wid)
    assert ws.get(wid)["name"] == "Shared" and next(w for w in ws.listing() if w["id"] == wid)["own_books"]
    new = Library(data_dir=folder)
    assert new.state["sources"] == [str(folder / "books")] and sorted(new.found()) == ["alpha", "beta"]
    assert new.state["persons"] == export.scoped_state(lib, {"alpha", "beta"})["persons"]       # the state is the zip's, not merged with anything
    assert new.state["settings"] == lib.state["settings"] and "pinned" not in new.state["books"]["alpha"]
    assert set(new.ann["books"]) == {"alpha"} and new.ann["books"]["alpha"]["narrator"] == lib.ann["books"]["alpha"]["narrator"]
    assert new.book("alpha").n_tokens == lib.book("alpha").n_tokens
    assert ws.active == DEFAULT_ID and not list((tmp_path / "workspaces").glob("*.importing"))   # importing doesn't switch by itself


def test_topic_models_and_references_come_along(lib, ws, tmp_path):
    (lib.data_dir / "topics").mkdir()
    (lib.data_dir / "references").mkdir()
    (lib.data_dir / "topics" / "mine.json").write_text(json.dumps({"books": ["alpha"]}))
    (lib.data_dir / "references" / "words.json").write_text(json.dumps({"name": "Words"}))
    wid = ws.import_zip(make_zip(lib, ["alpha"], tmp_path / "out.zip"))
    assert (ws.folder(wid) / "topics" / "mine.json").exists() and (ws.folder(wid) / "references" / "words.json").exists()


def test_an_import_without_a_name_is_named_by_its_date_and_repeats_get_their_own_workspace(lib, ws, tmp_path):
    zip_path = make_zip(lib, ["alpha"], tmp_path / "out.zip")
    a = ws.import_zip(zip_path)
    assert ws.get(a)["name"].startswith("Imported 20")
    with pytest.raises(ValueError):
        ws.import_zip(zip_path)                                                                   # the same default name again
    b = ws.import_zip(zip_path, name="Second")
    assert ws.folder(a) != ws.folder(b)


@pytest.mark.parametrize("what, make", [
    ("not a zip", lambda src, dst: (dst.write_bytes(b"hello"), dst)[1]),
    ("no manifest", lambda src, dst: rewrite(src, dst, lambda n, d: None if n == "manifest.json" else d)),
    ("no state", lambda src, dst: rewrite(src, dst, lambda n, d: None if n == "state/library.json" else d)),
    ("other format", lambda src, dst: rewrite(src, dst, lambda n, d: json.dumps({**json.loads(d), "format": 99}).encode() if n == "manifest.json" else d)),
    ("a book without its tokens", lambda src, dst: rewrite(src, dst, lambda n, d: None if n.endswith("alpha.tokens") else d)),
    ("damaged state", lambda src, dst: rewrite(src, dst, lambda n, d: b"{nope" if n == "state/library.json" else d)),
    ("no books", lambda src, dst: rewrite(src, dst, lambda n, d: json.dumps({"format": export.FORMAT, "books": {}}).encode() if n == "manifest.json" else d)),
])
def test_a_zip_that_is_not_a_usable_export_is_refused_and_leaves_nothing(what, make, lib, ws, tmp_path):
    good = make_zip(lib, ["alpha"], tmp_path / "good.zip")
    bad = make(good, tmp_path / "bad.zip")
    with pytest.raises(ValueError):
        ws.import_zip(bad, name="Broken")
    assert [w["id"] for w in ws.listing()] == [DEFAULT_ID]
    assert not (tmp_path / "workspaces").exists() or not list((tmp_path / "workspaces").iterdir())


def test_only_the_known_files_of_a_zip_are_unpacked(lib, ws, tmp_path):
    good = make_zip(lib, ["alpha"], tmp_path / "good.zip")
    sneaky = tmp_path / "sneaky.zip"
    with zipfile.ZipFile(good) as a, zipfile.ZipFile(sneaky, "w") as b:
        for n in a.namelist():
            b.writestr(n, a.read(n))
        for n in ("../evil.txt", "books/../evil2.txt", "/abs.txt", "notes.txt", "books/alpha/sub/deep.txt"):
            b.writestr(n, "x")
    wid = ws.import_zip(sneaky, name="Sneaky")
    folder = ws.folder(wid)
    assert not (tmp_path / "evil.txt").exists() and not (folder / "evil2.txt").exists() and not (tmp_path / "workspaces" / "evil.txt").exists()
    assert sorted(p.name for p in folder.iterdir()) == ["annotations.json", "books", "library.json"]


# ---------- the routes ----------
def titles(client):
    """The books of the open workspace, as the library page lists them: {id: title}."""
    return {b["id"]: b["title"] for b in client.get("/api/library").json()["books"]}


def upload(client, zip_path, name="Shared", status=200):
    """Import an export zip through the route (the zip is the raw request body)."""
    r = client.post("/api/workspaces/import", params={"name": name}, content=zip_path.read_bytes())
    assert r.status_code == status, r.text[:300]
    return r.json()


def test_routes_list_create_rename_and_forget(client):
    first = client.get("/api/workspaces").json()
    assert [(w["id"], w["active"]) for w in first["workspaces"]] == [(DEFAULT_ID, True)]
    made = client.post("/api/workspaces", json={"name": "Austen", "sources": ["~/nowhere"]}).json()
    assert made["id"] == "austen" and [w["name"] for w in made["workspaces"]] == ["Default", "Austen"]
    assert client.post("/api/workspaces", json={"name": "austen"}).status_code == 400                   # a repeated name
    assert client.post("/api/workspaces", json={"name": "X", "sources": "a string"}).status_code == 400
    assert client.post("/api/workspaces/austen", json={"name": "Emma"}).json()["workspaces"][1]["name"] == "Emma"
    assert client.post("/api/workspaces/nope", json={"name": "x"}).status_code == 404
    assert client.post("/api/workspaces/forget", json={"id": DEFAULT_ID}).status_code == 400
    assert [w["id"] for w in client.post("/api/workspaces/forget", json={"id": "austen"}).json()["workspaces"]] == [DEFAULT_ID]
    assert client.post("/api/workspaces/forget", json={"id": "austen"}).status_code == 404
    assert client.post("/api/workspaces/forget", json={}).status_code == 400


def test_importing_through_the_route_and_switching_between_workspaces(client, lib, tmp_path):
    zip_path = make_zip(lib, ["alpha", "beta"], tmp_path / "out.zip")
    assert upload(client, zip_path, name="Shared")["id"] == "shared"
    assert client.get("/api/workspaces").json()["workspaces"][1]["own_books"] is True
    assert set(titles(client)) == {"alpha", "beta", "gamma"}                                         # importing doesn't switch
    (tmp_path / "junk.zip").write_bytes(b"not a zip")
    assert "isn't a zip" in upload(client, tmp_path / "junk.zip", name="Junk", status=400)["detail"]

    client.post("/api/settings", json={"conv_gap": 77})                                              # work done in Default...
    client.post("/api/books/alpha", json={"title": "Default's alpha"})
    ref = client.post("/api/refs", json={"name": "Words", "files": [{"name": "w.txt", "text": "one two three"}]}).json()
    assert client.get("/api/refs").json()["rows"][0]["name"] == "Words"

    switched = client.post("/api/workspaces/activate", json={"id": "shared"}).json()
    assert [w["id"] for w in switched["workspaces"] if w["active"]] == ["shared"]
    lib_page = client.get("/api/library").json()
    assert set(titles(client)) == {"alpha", "beta"} and lib_page["settings"]["conv_gap"] != 77        # ...stays in Default
    assert titles(client)["alpha"] == "Alpha"                                                        # the imported workspace's own details
    assert client.get("/api/refs").json()["rows"] == []
    assert client.post("/api/units", json={"books": ["alpha", "beta"]}).json()["rows"]               # analysis runs on the imported books
    assert client.post("/api/units", json={"books": ["gamma"]}).status_code == 400                   # gamma isn't in this workspace
    client.post("/api/books/alpha", json={"title": "Shared's alpha"})

    client.post("/api/workspaces/activate", json={"id": DEFAULT_ID})
    assert set(titles(client)) == {"alpha", "beta", "gamma"} and titles(client)["alpha"] == "Default's alpha"
    assert client.get("/api/library").json()["settings"]["conv_gap"] == 77
    assert [r["id"] for r in client.get("/api/refs").json()["rows"]] == [ref["id"]]
    assert Library(data_dir=lib.data_dir.parent / "workspaces" / "shared").meta("alpha")["title"] == "Shared's alpha"   # saved in its own folder


def test_the_active_workspace_is_remembered_by_the_list(client, lib, tmp_path):
    upload(client, make_zip(lib, ["alpha"], tmp_path / "out.zip"))
    client.post("/api/workspaces/activate", json={"id": "shared"})
    assert Workspaces(tmp_path / "workspaces.json", default_data=lib.data_dir).active == "shared"


def test_a_workspace_that_cannot_be_read_is_refused_and_the_current_one_stays_open(client, lib, tmp_path):
    upload(client, make_zip(lib, ["alpha"], tmp_path / "out.zip"))
    (tmp_path / "workspaces" / "shared" / "library.json").write_text("{damaged")
    r = client.post("/api/workspaces/activate", json={"id": "shared"})
    assert r.status_code == 400 and "library.json" in r.json()["detail"]
    assert client.get("/api/workspaces").json()["workspaces"][0]["active"] and set(titles(client)) == {"alpha", "beta", "gamma"}
    assert client.post("/api/workspaces/activate", json={"id": "nope"}).status_code == 404
    import shutil
    shutil.rmtree(tmp_path / "workspaces" / "shared")
    assert client.post("/api/workspaces/activate", json={"id": "shared"}).status_code == 400          # its folder is gone


def test_deleting_through_the_route_asks_for_the_name(client, lib, tmp_path):
    upload(client, make_zip(lib, ["alpha"], tmp_path / "out.zip"))
    folder = tmp_path / "workspaces" / "shared"
    assert client.post("/api/workspaces/delete", json={"id": "shared", "name": "shared"}).status_code == 400
    assert client.post("/api/workspaces/delete", json={"id": "shared"}).status_code == 400
    assert folder.is_dir()
    client.post("/api/workspaces/activate", json={"id": "shared"})
    assert client.post("/api/workspaces/delete", json={"id": "shared", "name": "Shared"}).status_code == 400     # in use
    client.post("/api/workspaces/activate", json={"id": DEFAULT_ID})
    assert client.post("/api/workspaces/delete", json={"id": DEFAULT_ID, "name": "Default"}).status_code == 400
    r = client.post("/api/workspaces/delete", json={"id": "shared", "name": "Shared"})
    assert r.status_code == 200 and not folder.exists() and [w["id"] for w in r.json()["workspaces"]] == [DEFAULT_ID]
    assert lib.data_dir.is_dir()


def test_switching_while_the_analyser_is_in_use(client, lib, tmp_path):
    """Requests running while workspaces are switched may fail with a message, but must not wedge the analyser: afterwards it serves
    the workspace last chosen, with that workspace's own books."""
    upload(client, make_zip(lib, ["alpha", "beta"], tmp_path / "out.zip"))
    stop, errors = threading.Event(), []

    def hammer():
        while not stop.is_set():
            r = client.post("/api/units", json={"books": ["alpha", "beta"]})
            if r.status_code not in (200, 400):
                errors.append((r.status_code, r.text[:200]))

    threads = [threading.Thread(target=hammer) for _ in range(3)]
    for t in threads:
        t.start()
    for wid in ["shared", DEFAULT_ID] * 5:
        assert client.post("/api/workspaces/activate", json={"id": wid}).status_code == 200
    stop.set()
    for t in threads:
        t.join()
    assert not errors, errors[:3]
    client.post("/api/workspaces/activate", json={"id": "shared"})
    assert set(titles(client)) == {"alpha", "beta"} and client.post("/api/units", json={"books": ["alpha", "beta"]}).status_code == 200


def test_the_page_carries_the_id_of_the_open_workspace(client, lib, tmp_path):
    """The browser keeps its remembered settings per workspace, keyed by this id."""
    assert 'window.WORKSPACE = "default";' in client.get("/").text
    upload(client, make_zip(lib, ["alpha"], tmp_path / "out.zip"))
    client.post("/api/workspaces/activate", json={"id": "shared"})
    page = client.get("/")
    assert 'window.WORKSPACE = "shared";' in page.text and "window.WORKSPACE = null" not in page.text
    assert page.headers["cache-control"] == "no-cache" and "<main" in page.text
