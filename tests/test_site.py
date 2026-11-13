"""Buildings, floors and floor plans (server/site.py, server/plan.py): what an empty site folder gives, the example
building, every rule a plan must pass before it is saved, and how known rooms, room names and stair names follow the
saved plans. Each test has its own empty site folder."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import logic, main, plan, site, validate
from tests.util import LOCAL_URL

TOKEN = "site-token-0123456789ab"


@pytest.fixture
def folder(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_DIR", str(tmp_path / "site"))
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.delenv("EXAMPLE_BUILDING", raising=False)
    monkeypatch.delenv("BUILDING_NAME", raising=False)
    monkeypatch.delenv("LEVEL_NAME", raising=False)
    plan.refresh()
    yield tmp_path / "site"
    monkeypatch.undo()
    plan.refresh()


def write_site(folder, buildings):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "site.json").write_text(json.dumps({"buildings": buildings}), encoding="utf-8")


def write_version(folder, floor_id, version, doc, by="admin", ts=1_800_000_000, note=""):
    d = folder / "plans" / floor_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"v{version:06d}.json").write_text(json.dumps({"version": version, "saved_ts": ts, "saved_by": by, "note": note,
                                                        "plan": doc}), encoding="utf-8")


def two_floors(folder, f2_plan=None):
    write_site(folder, [{"id": "b1", "name": None, "code": "", "floors": [{"id": "f1", "name": None, "level": None},
                                                                          {"id": "f2", "name": "Level 5", "level": 5}]}])
    if f2_plan is not None:
        write_version(folder, "f2", 1, f2_plan)
    plan.refresh()


def api(ip="192.168.1.40"):
    return TestClient(main.app, client=(ip, 5000), base_url=LOCAL_URL)


def keys(errors):
    return sorted(e["key"] for e in errors)


def base():
    return site.builtin_plan()


# --- an empty folder is today's console ---

def test_an_empty_folder_gives_the_built_in_building_floor_and_plan(folder):
    assert not folder.exists()
    real = site.buildings(with_example=False)
    assert real == [{"id": "b1", "name": "Demo Building", "code": "", "example": False,
                     "floors": [{"id": "f1", "name": "Level 4", "level": 4}]}]
    doc = site.plan("f1")
    assert doc["version"] == 0 and doc["saved_by"] is None and doc["plan"] == base()
    assert "_about" not in doc["plan"] and set(doc["plan"]["rooms"]) == {"room1", "room2", "room3"}
    assert site.versions("f1") == [{"version": 0, "saved_ts": None, "saved_by": None, "note": "", "rooms": 3}]
    assert set(plan.PLAN["rooms"]) == {"room1", "room2", "room3"} and plan.exit_name("room1") == "Stair B"
    assert validate.known_rooms() >= {"room1", "room2", "room3"}
    assert not folder.exists()  # reading never writes


def test_the_built_in_names_follow_the_configuration(folder, monkeypatch):
    monkeypatch.setenv("BUILDING_NAME", "Block N28")
    monkeypatch.setenv("LEVEL_NAME", "Level 7")
    site.reset()
    b = site.buildings(with_example=False)[0]
    assert b["name"] == "Block N28" and b["floors"][0] == {"id": "f1", "name": "Level 7", "level": 7}


def test_the_example_building_is_read_only_data_without_sensors(folder, monkeypatch):
    ex = site.buildings()[-1]
    assert ex["id"] == "example" and ex["example"] is True and ex["code"] == "EX-01"
    assert ex["name"] == "Example Tower (example data)" and len(ex["floors"]) == 12
    assert ex["floors"][6] == {"id": "ex-7", "name": "Level 7", "level": 7}
    p = site.plan("ex-7")["plan"]
    assert set(p["rooms"]) == {f"ex-l07-{c}" for c in "abcdefgh"} and p["rooms"]["ex-l07-a"]["name"] == "Room 7.01"
    assert site.validate_plan(site.corridor_plan("new", 3), "f9") == []  # the template itself passes every rule
    assert not any(r.startswith("ex-") for r in plan.PLAN["rooms"])  # not on the merged view ...
    assert "ex-l07-a" not in validate.known_rooms()                   # ... so no board can report for them
    assert all(not any("link" in r for r in site.plan(f["id"])["plan"]["rooms"].values()) for f in ex["floors"])
    monkeypatch.setenv("EXAMPLE_BUILDING", "off")
    assert [b["id"] for b in site.buildings()] == ["b1"]


def test_a_saved_version_replaces_the_built_in_plan_and_the_server_follows(folder):
    doc = base()
    doc["rooms"]["lab9"] = {"name": "Lab 9", "x": 620, "y": 310, "w": 120, "h": 230, "door": {"x": 680, "side": "n"}, "exit": "stairB"}
    doc["other"] = [o for o in doc["other"] if o.get("label") != "plan.pantry"]
    write_version(folder, "f1", 1, doc, by="warden1")
    plan.refresh()
    assert site.plan("f1")["version"] == 1 and site.plan("f1")["saved_by"] == "warden1"
    assert "lab9" in validate.known_rooms() and plan.room_names()["lab9"] == "Lab 9"
    assert plan.exit_name("lab9", "ms") == "Tangga B" and plan.floor_of("lab9") == "f1"
    assert [v["version"] for v in site.versions("f1")] == [1, 0]
    assert site.version_plan("f1", 0) == base()  # the built-in plan can always be restored


def test_rooms_and_stairs_of_every_floor_reach_the_chat(folder):
    f2 = site.corridor_plan("l5", 5)
    f2["exits"]["stairA"] = {**f2["exits"]["stairA"], "label": None, "name": "Fire stair West"}
    f2["exits"]["stairA"].pop("label")
    two_floors(folder, f2)
    assert plan.exit_name("l5-a") == "Fire stair West" and plan.exit_name("room1") == "Stair B"
    assert {"stairA", "stairB", "f2:stairA", "f2:stairB"} <= set(plan.PLAN["exits"])
    assert logic._exits_named("Use Fire stair West, then Stair B.") == {"f2:stairA", "stairB", "f2:stairB"}
    assert "l5-a" in validate.known_rooms() and plan.room_names()["l5-a"] == "Room 5.01"


def test_a_folder_that_cannot_be_read_keeps_the_built_in_plan(folder):
    folder.mkdir(parents=True)
    (folder / "site.json").write_text("{not json", encoding="utf-8")
    plan.refresh()
    assert set(plan.PLAN["rooms"]) == {"room1", "room2", "room3"} and plan.exit_name("room2") == "Stair A"


# --- the rules a plan must pass ---

def test_the_built_in_plan_passes_every_rule(folder):
    assert site.validate_plan(base(), "f1") == []


@pytest.mark.parametrize("change,key", [
    (lambda p: p["rooms"]["room1"].update(x=500), "site.err_overlap"),                       # into Hall A
    (lambda p: p["rooms"]["room2"].update(x=60), "site.err_overlap"),                        # into Stair A
    (lambda p: p.update(exits={}), "site.err_no_exit"),
    (lambda p: p["rooms"]["room1"].update(exit="stairZ"), "site.err_exit_missing"),
    (lambda p: p["rooms"]["room1"].update(x=900), "site.err_outside"),
    (lambda p: p["rooms"]["room3"].update(w=30), "site.err_small"),
    (lambda p: p["rooms"].update({"Bad ID": p["rooms"].pop("room3")}), "site.err_id"),
    (lambda p: p["rooms"]["room1"].update(name=""), "site.err_name"),
    (lambda p: p["rooms"]["room1"].update(name="x" * 41), "site.err_name"),
    (lambda p: p["rooms"]["room1"].update(link={"send": {"x": 548, "y": 196}, "recv": {"x": 560, "y": 196}}), "site.err_link"),
    (lambda p: p["rooms"]["room1"].update(link={"send": {"x": 548, "y": 196}, "recv": {"x": 900, "y": 196}}), "site.err_link"),
    (lambda p: p["rooms"]["room1"].update(door={"x": 100, "side": "s"}), "site.err_door"),
    (lambda p: p["rooms"]["room1"].update(door={"x": 700, "side": "e"}), "site.err_door"),
    (lambda p: p["rooms"]["room1"].update(area_m2=0), "site.err_area"),
    (lambda p: p["rooms"]["room1"].update(x="520"), "site.err_shape_of"),
    (lambda p: p["rooms"]["room1"].update(w=float("nan")), "site.err_shape_of"),
    (lambda p: p.update(background={"image": "a" * 64 + ".png", "opacity": 0.5}), "site.err_background"),
    (lambda p: p["other"].append({"name": "", "x": 0, "y": 0, "w": 50, "h": 50}), "site.err_name"),
    (lambda p: p.update(viewBox=[0, 0, 800, 600]), "site.err_shape"),
    (lambda p: p.update(rooms=[]), "site.err_shape"),
    (lambda p: p.update(script="<script>"), "site.err_shape"),                               # fields that are not drawing data
    (lambda p: p["outline"].update(onload="x"), "site.err_shape"),
    (lambda p: p["rooms"]["room1"].update(html="<b>"), "site.err_shape_of"),
    (lambda p: p["exits"]["stairA"].update(url="http://x"), "site.err_shape_of"),
    (lambda p: p["other"][0].update(extra=1), "site.err_shape_of"),
    (lambda p: p["rooms"]["room1"]["door"].update(width=3), "site.err_door"),
    (lambda p: p["rooms"]["room1"]["link"].update(note="x"), "site.err_link"),
    (lambda p: p["rooms"]["room1"]["link"]["send"].update(z=1), "site.err_link"),
])
def test_each_rule_refuses_a_plan_that_breaks_it(folder, change, key):
    doc = base()
    change(doc)
    assert key in keys(site.validate_plan(doc, "f1"))


def test_touching_rooms_are_fine_and_every_problem_comes_back_at_once(folder):
    doc = base()
    assert doc["rooms"]["room2"]["x"] + doc["rooms"]["room2"]["w"] == doc["rooms"]["room1"]["x"]  # Hall A touches Lab 2
    assert site.validate_plan(doc, "f1") == []
    doc["rooms"]["room1"].update(x=500, exit="nowhere", name="")
    doc["exits"]["stairB"].update(w=10)  # too narrow, and its door is now outside it
    assert keys(site.validate_plan(doc, "f1")) == ["site.err_door", "site.err_exit_missing", "site.err_name", "site.err_overlap",
                                                   "site.err_small"]


def test_more_than_sixty_rooms_or_a_plan_over_64_kb_is_refused(folder):
    doc = site.blank_plan()
    doc["exits"]["s"] = {"name": "Stair", "x": 0, "y": 0, "w": 40, "h": 40}
    for i in range(61):
        doc["rooms"][f"r{i}"] = {"name": f"R{i}", "x": 40 + (i % 20) * 47, "y": 50 + (i // 20) * 120, "w": 45, "h": 100, "exit": "s"}
    assert keys(site.validate_plan(doc, "f9")) == ["site.err_too_many"]
    big = base()
    big["other"].append({"name": "x", "x": 0, "y": 0, "w": 50, "h": 50, "notes": "y" * 70000})
    assert keys(site.validate_plan(big, "f1")) == ["site.err_too_large"]


def test_a_room_id_used_on_another_floor_is_refused(folder):
    two_floors(folder, site.corridor_plan("l5", 5))
    doc = base()
    doc["rooms"]["l5-a"] = doc["rooms"].pop("room3")
    errors = site.validate_plan(doc, "f1")
    assert errors == [{"key": "site.err_taken", "values": {"id": "l5-a", "floor": "Demo Building, Level 5"}}]
    doc["rooms"]["ex-l03-b"] = doc["rooms"].pop("l5-a")  # the example building's IDs are taken too
    assert keys(site.validate_plan(doc, "f1")) == ["site.err_taken"]


def test_a_room_with_a_reporting_sensor_cannot_be_removed(folder):
    doc = base()
    del doc["rooms"]["room1"]
    assert site.validate_plan(doc, "f1", live_rooms={"room2"}) == []  # room1 reports nothing now: it may go
    errors = site.validate_plan(doc, "f1", live_rooms={"room1"})
    assert errors == [{"key": "site.err_live", "values": {"id": "room1", "name": "Lab 2"}}]
    renamed = base()
    renamed["rooms"]["lab2"] = renamed["rooms"].pop("room1")  # a new ID is a removal of the old one
    assert keys(site.validate_plan(renamed, "f1", live_rooms={"room1"})) == ["site.err_live"]
    moved = base()
    moved["rooms"]["room1"].update(name="Lab Two")  # renaming the name only is fine
    assert site.validate_plan(moved, "f1", live_rooms={"room1"}) == []


def test_messages_come_in_the_page_language(folder):
    doc = base()
    doc["rooms"]["room1"].update(x=500)
    en = site.messages(site.validate_plan(doc, "f1"))
    ms = site.messages(site.validate_plan(doc, "f1"), "ms")
    assert en[0]["message"] == "Hall A and Lab 2 overlap." and ms[0]["message"] == "Hall A dan Lab 2 bertindih."


# --- the read API ---

def test_site_api_lists_buildings_floors_and_the_example(folder):
    out = api().get("/api/site").json()
    assert out["default_floor"] == "f1" and out["editor"] is True
    b1, ex = out["buildings"]
    assert b1["floors"] == [{"id": "f1", "name": "Level 4", "level": 4, "rooms": 3, "version": 0}]
    assert ex["example"] is True and ex["floors"][0] == {"id": "ex-1", "name": "Level 1", "level": 1, "rooms": 8, "version": 0}


def test_info_says_which_floor_each_room_is_on_and_its_exit_in_the_page_language(folder):
    two_floors(folder, site.corridor_plan("l5", 5))
    en, ms = api().get("/api/info").json(), api().get("/api/info?lang=ms").json()
    assert en["room_floors"]["room1"] == "f1" and en["room_floors"]["l5-a"] == "f2"
    assert en["room_exits"]["room1"] == "Stair B" and ms["room_exits"]["room1"] == "Tangga B"
    assert en["room_exits"]["l5-h"] == "Stair B" and not any(r.startswith("ex-") for r in en["room_floors"])


def test_floor_plan_api(folder):
    out = api().get("/api/floors/f1/plan").json()
    assert out["floor_id"] == "f1" and out["version"] == 0 and out["plan"] == base()
    assert api().get("/api/floors/ex-3/plan").json()["plan"]["rooms"]["ex-l03-a"]["name"] == "Room 3.01"
    missing = api().get("/api/floors/f77/plan")
    assert missing.status_code == 404 and missing.json()["detail"] == "There is no floor f77."
    assert api().get("/api/floors/..%2Fsite/plan").status_code == 404


def test_versions_are_for_admins_only(folder):
    assert api().get("/api/floors/f1/versions").status_code == 401
    out = api().get("/api/floors/f1/versions", headers={"X-Admin-Token": TOKEN}).json()
    assert out == {"floor_id": "f1", "versions": [{"version": 0, "saved_ts": None, "saved_by": None, "note": "", "rooms": 3}]}


def test_viewer_token_guards_the_site_reads(folder, monkeypatch):
    monkeypatch.setenv("VIEWER_TOKEN", "viewer-token-0123456789")
    for path in ("/api/site", "/api/floors/f1/plan"):
        assert api().get(path).status_code == 401
        assert api().get(path, headers={"X-Viewer-Token": "viewer-token-0123456789"}).status_code == 200


def test_images_are_served_only_by_their_hash_name_and_never_as_a_page(folder):
    name = "ab" * 32 + ".png"
    (folder / "images").mkdir(parents=True)
    (folder / "images" / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
    out = api().get(f"/api/site/images/{name}")
    assert out.status_code == 200 and out.headers["content-type"] == "image/png"
    assert out.headers["x-content-type-options"] == "nosniff" and out.headers["content-security-policy"] == "default-src 'none'"
    for bad in ("AB" * 32 + ".png", "ab" * 32 + ".svg", "ab" * 32 + ".png.html", "site.json", "..%2Fsite.json", "ab" * 31 + ".png"):
        assert api().get(f"/api/site/images/{bad}").status_code == 404, bad


def test_the_plan_does_not_change_while_it_is_read(folder):
    first = copy.deepcopy(site.plan("f1"))
    api().get("/api/floors/f1/plan")
    assert site.plan("f1") == first


# --- the same cases for the server and the editor (web/src/test/plan-editor.test.tsx reads this file too) ---

CASES = json.loads((Path(__file__).parent / "fixtures" / "plan_cases.json").read_text(encoding="utf-8"))["cases"]


def apply_case(doc, case):
    """A case's changes on a copy of the plan: set (dotted path), del, rename (a room ID)."""
    doc = copy.deepcopy(doc)

    def walk(path):
        *head, last = path.split(".")
        node = doc
        for part in head:
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node, (int(last) if isinstance(node, list) else last)

    for path, value in case.get("set", {}).items():
        node, key = walk(path)
        node[key] = value
    for path in case.get("del", []):
        node, key = walk(path)
        del node[key]
    if "rename" in case:
        old, new = case["rename"]
        doc["rooms"] = {new if k == old else k: v for k, v in doc["rooms"].items()}
    return doc


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_plan_cases(folder, case):
    assert sorted(e["key"] for e in site.validate_plan(apply_case(base(), case), "f1")) == case["keys"]


def test_the_example_building_is_named_in_the_page_language(folder):
    ms = api().get("/api/site?lang=ms").json()["buildings"][-1]
    assert ms["name"] == "Menara Contoh (data contoh)" and ms["floors"][6]["name"] == "Aras 7"
    plan_ms = api().get("/api/floors/ex-7/plan?lang=ms").json()["plan"]
    assert plan_ms["rooms"]["ex-l07-a"]["name"] == "Bilik 7.01"
    assert api().get("/api/floors/ex-7/plan").json()["plan"]["rooms"]["ex-l07-a"]["name"] == "Room 7.01"
    assert api().get("/api/site?lang=ms").json()["buildings"][0]["name"] == "Demo Building"  # typed or configured names stay as written


def test_a_new_building_gets_its_first_floor_named_in_the_admins_language(folder):
    out = api().post("/api/site/buildings?lang=ms", json={"name": "Blok N28", "code": "N28"},
                     headers={"X-Admin-Token": TOKEN}).json()
    floors = {f["id"]: f["name"] for b in api().get("/api/site").json()["buildings"] for f in b["floors"]}
    assert floors[out["floor_id"]] == "Aras 1"


def test_a_damaged_site_file_or_version_falls_back_instead_of_failing(folder):
    folder.mkdir(parents=True)
    (folder / "site.json").write_text('{"buildings": "oops"}', encoding="utf-8")
    site.reset()
    out = api().get("/api/site")
    assert out.status_code == 200 and out.json()["buildings"][0]["floors"][0]["id"] == "f1"
    (folder / "site.json").unlink()
    write_version(folder, "f1", 1, site.corridor_plan("good", 4))
    (folder / "plans" / "f1" / "v000002.json").write_text("{cut off", encoding="utf-8")
    site.reset()
    doc = api().get("/api/floors/f1/plan").json()
    assert doc["version"] == 1 and "good-a" in doc["plan"]["rooms"]  # the newest version that can be read
