"""The floor plan write API: who may write, what is refused and with which status, versions and restore, the audit
log, and how the rest of the server (known rooms, names, the chat's stair names) follows a saved plan."""
import copy
import time

import pytest
from fastapi.testclient import TestClient

from server import config, logic, main, plan, site, store, validate
from tests.util import LOCAL_URL

TOKEN = "siteapi-token-0123456789"
H = {"X-Admin-Token": TOKEN}


@pytest.fixture
def folder(monkeypatch, tmp_path):
    monkeypatch.setenv("SITE_DIR", str(tmp_path / "site"))
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.delenv("PLAN_EDITOR", raising=False)
    plan.refresh()
    yield tmp_path / "site"
    monkeypatch.undo()
    plan.refresh()


def api(ip="192.168.1.40"):
    return TestClient(main.app, client=(ip, 5000), base_url=LOCAL_URL)


def with_lab9():
    doc = site.builtin_plan()
    doc["other"] = [o for o in doc["other"] if o.get("label") != "plan.pantry"]
    doc["rooms"]["lab9"] = {"name": "Lab 9", "x": 620, "y": 310, "w": 240, "h": 230, "door": {"x": 680, "side": "n"},
                            "exit": "stairB", "link": {"send": {"x": 650, "y": 500}, "recv": {"x": 830, "y": 500}}, "area_m2": 40}
    return doc


def save(doc, base=0, lang="en", **kw):
    return api(**kw).put(f"/api/floors/f1/plan?lang={lang}", json={"plan": doc, "note": "Lab 9 opened", "base_version": base}, headers=H)


def test_a_saved_plan_becomes_the_floor_and_the_server_follows(folder):
    assert "lab9" not in validate.known_rooms()
    out = save(with_lab9())
    assert out.status_code == 200 and out.json() == {"ok": True, "floor_id": "f1", "version": 1}
    assert api().get("/api/floors/f1/plan").json()["plan"]["rooms"]["lab9"]["name"] == "Lab 9"
    assert "lab9" in validate.known_rooms() and config.display_names()["lab9"] == "Lab 9"
    assert plan.exit_name("lab9", "ms") == "Tangga B"
    assert api().get("/api/info").json()["room_floors"]["lab9"] == "f1"
    assert api().get("/api/site").json()["buildings"][0]["floors"][0] == {"id": "f1", "name": "Level 4", "level": 4, "rooms": 4, "version": 1}
    versions = api().get("/api/floors/f1/versions", headers=H).json()["versions"]
    assert [(v["version"], v["saved_by"], v["note"]) for v in versions] == [(1, "admin", "Lab 9 opened"), (0, None, "")]
    entry = store.audit_log()[0]
    assert entry["action"] == "plan_save" and entry["floor"] == "f1" and entry["version"] == 1 and entry["by"] == "admin"


def test_a_board_can_report_for_a_room_once_it_is_drawn(folder):
    report = {"service_id": "csi", "properties": {"room_id": "lab9", "ts": int(time.time()), "motion_mean": 0.1, "motion_std": 0.2,
                                                  "amp_var": 0.1, "rssi_mean": -50.0, "n_packets": 500}}
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    body = {"resource": "device.property", "notify_data": {"body": {"services": [report]}}}
    assert local.post("/iotda", json=body).status_code == 422  # not on any plan yet: an unknown room
    save(with_lab9())
    assert local.post("/iotda", json=body).status_code == 200


def test_the_chat_names_a_stair_an_admin_typed(folder):
    doc = with_lab9()
    doc["exits"]["stairB"] = {k: v for k, v in doc["exits"]["stairB"].items() if k != "label"} | {"name": "East fire stair"}
    assert save(doc).status_code == 200
    assert plan.exit_name("room1") == "East fire stair" and plan.exit_name("lab9", "ms") == "East fire stair"
    assert logic._exits_named("Leave by the East fire stair.") == {"stairB"}


def test_a_plan_that_breaks_a_rule_is_refused_with_every_problem_and_nothing_changes(folder):
    doc = with_lab9()
    doc["rooms"]["lab9"]["x"] = 600          # into Room 3
    doc["rooms"]["room3"]["exit"] = "nowhere"
    out = save(doc)
    assert out.status_code == 422
    keys = sorted(e["key"] for e in out.json()["errors"])
    assert keys == ["site.err_exit_missing", "site.err_overlap"]
    assert "Room 3 and Lab 9 overlap." in out.json()["detail"]
    ms = save(doc, lang="ms").json()["errors"]
    assert any(e["message"] == "Room 3 dan Lab 9 bertindih." for e in ms)
    assert api().get("/api/floors/f1/plan").json()["version"] == 0 and "lab9" not in validate.known_rooms()
    assert not (folder / "plans").exists() and store.audit_log() == []


def test_a_room_with_a_sensor_reporting_cannot_be_drawn_away(folder):
    store.r.sadd("rooms", "room1")
    store.r.hset("room:room1", mapping={"headcount": 1, "count_ts": int(time.time())})
    doc = site.builtin_plan()
    del doc["rooms"]["room1"]
    out = save(doc)
    assert out.status_code == 422 and out.json()["errors"][0]["key"] == "site.err_live"
    assert out.json()["errors"][0]["message"] == "Lab 2 (room1) has a sensor reporting, so it cannot be removed."
    store.r.hset("room:room1", "count_ts", int(time.time()) - 3600)  # silent for an hour: it may go
    assert save(doc).status_code == 200


def test_a_save_on_top_of_someone_elses_is_refused(folder):
    assert save(with_lab9(), base=0).status_code == 200
    late = save(site.builtin_plan(), base=0)
    assert late.status_code == 409 and late.json()["detail"] == "Someone else saved this plan. Reload to see their version."
    assert api().get("/api/floors/f1/plan").json()["version"] == 1


def test_restore_makes_an_old_version_current_as_a_new_one(folder):
    save(with_lab9())
    out = api().post("/api/floors/f1/restore", json={"version": 0}, headers=H)
    assert out.status_code == 200 and out.json()["version"] == 2
    assert api().get("/api/floors/f1/plan").json()["plan"] == site.builtin_plan()
    assert "lab9" not in validate.known_rooms()
    assert [v["version"] for v in api().get("/api/floors/f1/versions", headers=H).json()["versions"]] == [2, 1, 0]
    assert store.audit_log()[0] | {"ts": 0, "ip": ""} == {"ts": 0, "ip": "", "action": "plan_restore", "by": "admin", "floor": "f1",
                                                           "version": 2, "from": 0}
    assert api().post("/api/floors/f1/restore", json={"version": 9}, headers=H).status_code == 404


def test_only_the_newest_thirty_versions_are_kept(folder, monkeypatch):
    monkeypatch.setattr(main, "live_room_ids", lambda: set())
    doc = site.builtin_plan()
    for i in range(32):
        doc["rooms"]["room3"]["name"] = f"Room 3 v{i}"
        site.save_plan("f1", copy.deepcopy(doc), "admin")
    numbers = [v["version"] for v in site.versions("f1")]
    assert numbers[0] == 32 and numbers[-2] == 3 and numbers[-1] == 0 and len(numbers) == 31  # 30 kept + built-in


def test_buildings_and_floors_can_be_added_and_renamed(folder):
    out = api().post("/api/site/buildings", json={"name": "Block N28", "code": "N28"}, headers=H).json()
    assert out == {"ok": True, "building_id": "b2", "floor_id": "f2"}
    floor = api().post("/api/site/buildings/b2/floors", json={"name": "Level 2", "level": 2}, headers=H).json()
    assert floor == {"ok": True, "floor_id": "f3"}
    assert api().put("/api/site/buildings/b1", json={"name": "Faculty of Computing", "code": "FC"}, headers=H).status_code == 200
    assert api().put("/api/site/floors/f1", json={"name": "Level 4 (labs)"}, headers=H).status_code == 200
    b1, b2, ex = api().get("/api/site").json()["buildings"]
    assert (b1["name"], b1["code"], b1["floors"][0]["name"], b1["floors"][0]["level"]) == ("Faculty of Computing", "FC", "Level 4 (labs)", 4)
    assert [f["id"] for f in b2["floors"]] == ["f2", "f3"] and b2["floors"][0]["rooms"] == 0
    assert ex["example"] is True
    assert api().get("/api/floors/f3/plan").json()["plan"]["rooms"] == {}
    assert [e["action"] for e in store.audit_log()] == ["site_rename", "site_rename", "site_add", "site_add"]


def test_names_codes_and_levels_are_checked(folder):
    for body in ({"name": ""}, {"name": "x" * 41}, {"name": "Ok", "code": "bad code!"}):
        out = api().post("/api/site/buildings", json=body, headers=H)
        assert out.status_code == 422, body
    assert api().post("/api/site/buildings/b1/floors", json={"name": "L", "level": 999}, headers=H).status_code == 422
    assert api().post("/api/site/buildings/b1/floors", json={"name": "L", "level": "2"}, headers=H).status_code == 422
    assert api().post("/api/site/buildings/b9/floors", json={"name": "L", "level": 2}, headers=H).status_code == 404


def test_the_example_building_is_read_only(folder):
    doc = site.plan("ex-2")["plan"]
    assert api().put("/api/floors/ex-2/plan", json={"plan": doc, "base_version": 0}, headers=H).status_code == 409
    assert api().post("/api/floors/ex-2/restore", json={"version": 0}, headers=H).status_code == 409
    assert api().post("/api/site/buildings/example/floors", json={"name": "L13", "level": 13}, headers=H).status_code == 409
    assert api().put("/api/site/buildings/example", json={"name": "Mine now"}, headers=H).status_code == 409
    out = api().put("/api/site/floors/ex-1", json={"name": "Mine"}, headers=H)
    assert out.status_code == 409 and out.json()["detail"] == "The example building cannot be changed."


WRITES = [("put", "/api/floors/f1/plan", {"plan": {}, "base_version": 0}), ("post", "/api/floors/f1/restore", {"version": 0}),
          ("post", "/api/site/buildings", {"name": "B"}), ("post", "/api/site/buildings/b1/floors", {"name": "L", "level": 1}),
          ("put", "/api/site/buildings/b1", {"name": "B"}), ("put", "/api/site/floors/f1", {"name": "L"})]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_every_write_needs_an_admin(folder, method, path, body):
    assert getattr(api(), method)(path, json=body).status_code == 401
    assert getattr(api(), method)(path, json=body, headers={"X-Admin-Token": "wrong-token-0123456789"}).status_code == 401
    assert not (folder / "site.json").exists() and not (folder / "plans").exists()


@pytest.mark.parametrize("method,path,body", WRITES)
def test_every_write_from_another_website_is_refused(folder, method, path, body):
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    assert getattr(local, method)(path, json=body, headers={"Origin": "http://evil.example"}).status_code == 403


@pytest.mark.parametrize("method,path,body", WRITES)
def test_the_editor_switched_off_refuses_every_write(folder, monkeypatch, method, path, body):
    monkeypatch.setenv("PLAN_EDITOR", "off")
    assert getattr(api(), method)(path, json=body, headers=H).status_code == 404
    assert api().post("/api/floors/f1/image", content=b"x", headers=H).status_code == 404
    assert api().get("/api/site").json()["editor"] is False
    assert api().get("/api/floors/f1/plan").status_code == 200  # reading still works


def test_body_limits_are_per_path(folder):
    big_plan = with_lab9()
    big_plan["other"].append({"name": "x", "x": 0, "y": 0, "w": 50, "h": 50, "notes": "y" * 64600})  # over 64 KB, under the body cap
    out = save(big_plan)
    assert out.status_code == 422 and out.json()["errors"][0]["key"] == "site.err_too_large"  # read, then refused
    huge = {"plan": {"notes": "z" * 70000}, "base_version": 0}
    assert api().put("/api/floors/f1/plan", json=huge, headers=H).status_code == 413
    assert api().post("/api/site/buildings", json={"name": "B", "code": "x" * 5000}, headers=H).status_code == 413  # 4 KB here
    assert main.body_limit("PUT", "/api/floors/f1/plan") == main.MAX_PLAN_BODY
    assert main.body_limit("PUT", "//API/floors/f1/plan/") == main.MAX_PLAN_BODY
    assert main.body_limit("POST", "/api/floors/f1/plan") == main.MAX_BODY
    assert main.body_limit("POST", "/api/floors/../image") == main.MAX_BODY
    assert main.body_limit("POST", "/api/floors/f1/image") == main.MAX_IMAGE_BODY
    assert main.body_limit("POST", "/api/floors/f1/image/x") == main.MAX_BODY


def test_writes_count_against_the_admin_limit(folder):
    for _ in range(30):
        assert api().put("/api/site/floors/f1", json={"name": "Level 4"}, headers=H).status_code == 200
    assert api().put("/api/site/floors/f1", json={"name": "Level 4"}, headers=H).status_code == 429


def test_the_editor_opens_with_the_names_the_live_view_shows_and_an_unchanged_save_renames_nothing(folder, monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Demo Room")
    assert config.display_names()["room1"] == "Demo Room"
    doc = api().get("/api/floors/f1/plan").json()
    assert doc["plan"]["rooms"]["room1"]["name"] == "Demo Room"  # ROOM_NAMES over "Lab 2" on the built-in plan
    assert doc["plan"]["rooms"]["room2"]["name"] == "Hall A"     # no entry: the name on the plan
    out = api().put("/api/floors/f1/plan", json={"plan": doc["plan"], "base_version": doc["version"]}, headers=H)
    assert out.status_code == 200
    assert config.display_names()["room1"] == "Demo Room" and config.display_names()["room2"] == "Hall A"
    again = api().get("/api/floors/f1/plan").json()["plan"]["rooms"]
    assert again["room1"]["name"] == "Demo Room" and again["room2"]["name"] == "Hall A"
    monkeypatch.delenv("ROOM_NAMES")
    assert config.display_names()["room1"] == "Demo Room"  # the name the room had on screen is now on the plan
    assert api().get("/api/info").json()["room_names"]["room1"] == "Demo Room"


def test_a_rooms_capacity_is_saved_with_the_plan_and_its_change_is_in_the_audit_log(folder):
    doc = site.builtin_plan()
    doc["rooms"]["room1"]["capacity"] = 30
    assert save(doc).status_code == 200
    assert api().get("/api/floors/f1/plan").json()["plan"]["rooms"]["room1"]["capacity"] == 30
    assert store.audit_log()[0]["capacity"] == [["room1", None, 30]]
    doc = copy.deepcopy(doc)
    doc["rooms"]["room1"]["capacity"] = 24
    doc["rooms"]["room2"]["capacity"] = 120
    assert save(doc, base=1).status_code == 200
    assert store.audit_log()[0]["capacity"] == [["room1", 30, 24], ["room2", None, 120]]
    del doc["rooms"]["room1"]["capacity"]
    assert save(copy.deepcopy(doc), base=2).status_code == 200
    assert store.audit_log()[0]["capacity"] == [["room1", 24, None]]
    assert save(copy.deepcopy(doc), base=3).status_code == 200
    assert "capacity" not in store.audit_log()[0]  # a save that leaves every capacity alone says nothing about it


def test_a_capacity_that_is_not_a_whole_number_of_people_is_refused(folder):
    for bad in (0, -3, 1001, 12.5, "30", True):
        doc = site.builtin_plan()
        doc["rooms"]["room1"]["capacity"] = bad
        out = save(doc)
        assert out.status_code == 422, bad
        assert "capacity" in out.json()["errors"][0]["message"].lower() or "capacity" in str(out.json()).lower()
