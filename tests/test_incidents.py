"""Emergency and drill records: room accountability, drill mode, the report written at the end, and the automatic
snapshots. Runs on the in-memory Redis from conftest; MySQL writes are caught in a list."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from server import alerts, incident, main, store
from tests.util import LOCAL_URL

TOKEN = "warden-token-0123456789"
W = {"X-Admin-Token": TOKEN}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    monkeypatch.setenv("ADMIN_TOKENS", f"warden1:{TOKEN}")
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2,room2:Hall A,room3:Room 3")
    monkeypatch.setenv("INCIDENT_DIR", str(tmp_path))
    monkeypatch.setenv("OLLAMA_MODEL", "")
    monkeypatch.delenv("EMERGENCY_NUMBER", raising=False)
    monkeypatch.setattr(store, "_write", lambda sql, params: None)  # no MySQL
    return TestClient(main.app, client=("10.0.0.7", 5000), base_url=LOCAL_URL)


def count(room, n, ts=None):
    """An exact headcount report, as a counter would send it."""
    return main.process([{"service_id": "count", "properties": {"room_id": room, "ts": ts or int(time.time()),
                                                                 "headcount": n}}])


def start(api, drill=False):
    res = api.post("/api/emergency", json={"on": True, "drill": drill}, headers=W)
    assert res.status_code == 200, res.text
    return res.json()


def end(api):
    return api.post("/api/emergency", json={"on": False}, headers=W).json()


# --- drill mode ---

def test_drill_is_marked_everywhere_and_kept_apart(api, capsys):
    count("room1", 4)
    em = start(api, drill=True)
    assert em["on"] and em["drill"] and incident.valid_id(em["id"]) and "-drill-" in em["id"]
    rooms = api.get("/api/rooms").json()
    assert rooms["emergency"]["drill"] is True
    shown = api.get("/api/alerts").json()["alerts"]
    headcount = [a for a in shown if a["kind"] == "drill"]
    assert len(headcount) == 1 and headcount[0]["subject"] == "[DRILL] NADI: Emergency mode started"
    assert headcount[0]["severity"] == "info"  # never critical
    assert headcount[0]["message"].endswith("Lab 2: 4. This is a drill, not a real emergency.")
    assert all(a["drill"] for a in shown)  # every alert of the drill says so
    ms = api.get("/api/alerts?lang=ms").json()["alerts"]
    assert all(a["subject"].startswith("[LATIHAN]") for a in ms)
    out = capsys.readouterr().out
    assert "[ALERT] [DRILL] NADI: Emergency mode started" in out and "[AMARAN] [LATIHAN]" in out  # console
    assert store.audit_log()[0]["drill"] is True
    end(api)
    listing = api.get("/api/incidents").json()["incidents"]
    assert [r["kind"] for r in listing] == ["drill"]


def test_drill_alerts_reach_smn_marked_drill(api, monkeypatch):
    monkeypatch.setattr(alerts, "smn_enabled", lambda: True)
    sent = []
    monkeypatch.setattr(alerts, "_smn_publish", lambda subject, message: sent.append((subject, message)))
    start(api, drill=True)
    assert sent and all(s.startswith("[DRILL]") and "[LATIHAN]" in s for s, _ in sent)
    assert all("This is a drill" in m and "Ini ialah latihan" in m for _, m in sent)


def test_real_emergency_alert_is_critical_and_not_marked(api):
    count("room1", 2)
    em = start(api)
    assert em["drill"] is False and "-real-" in em["id"]
    a = [x for x in api.get("/api/alerts").json()["alerts"] if x["kind"] == "emergency"][0]
    assert a["severity"] == "critical" and not a["subject"].startswith("[DRILL]") and a["drill"] is False


def test_a_second_start_keeps_the_first_kind(api):
    first = start(api, drill=True)
    again = start(api, drill=False)  # pressing "real" during a drill does not turn it into another incident
    assert again["id"] == first["id"] and again["drill"] is True


def test_chat_says_drill(api):
    count("room1", 1)
    start(api, drill=True)
    a = api.post("/api/chat", json={"question": "Is the emergency on?"}, headers=W).json()["answer"]
    assert a.startswith("Whole building: A drill is running.")  # a drill locks the scope to the whole building
    assert a.endswith("By floor: Level 4: 1 person.")


# --- room accountability ---

def test_wardens_mark_rooms_and_marks_reset_when_it_ends(api):
    count("room1", 3)
    assert api.post("/api/emergency/rooms/room1", json={"status": "clear"}, headers=W).status_code == 409  # not on
    em = start(api)
    assert api.post("/api/emergency/rooms/room1", json={"status": "clear"}).status_code == 401  # admin only
    assert api.post("/api/emergency/rooms/room9", json={"status": "clear"}, headers=W).status_code == 422
    assert api.post("/api/emergency/rooms/room1", json={"status": "maybe"}, headers=W).status_code == 422
    out = api.post("/api/emergency/rooms/room1", json={"status": "help"}, headers=W).json()["accountability"]
    assert out["room1"]["status"] == "help" and out["room1"]["by"] == "warden1"
    api.post("/api/emergency/rooms/room2", json={"status": "clear"}, headers=W)
    marks = api.get("/api/rooms").json()["accountability"]
    assert marks["room1"]["status"] == "help" and marks["room2"]["status"] == "clear"  # every screen sees it
    api.post("/api/emergency/rooms/room2", json={"status": None}, headers=W)
    assert "room2" not in api.get("/api/rooms").json()["accountability"]
    actions = [(e["action"], e.get("room")) for e in store.audit_log()]
    assert ("room_help", "room1") in actions and ("room_clear", "room2") in actions and ("room_reset", "room2") in actions
    assert all(e["incident"] == em["id"] for e in store.audit_log() if e["action"].startswith("room_"))
    end(api)
    assert api.get("/api/rooms").json()["accountability"] == {}
    start(api)
    assert api.get("/api/rooms").json()["accountability"] == {}  # the next emergency starts with no marks


# --- the report ---

def test_report_has_times_to_zero_marks_offline_rooms_and_acks(api, monkeypatch):
    now = int(time.time())
    count("room1", 5, now - 2)
    count("room2", 2, now - 2)
    count("room3", 0, now - 2)
    em = start(api)
    started = em["since"]
    api.post("/api/emergency/rooms/room2", json={"status": "clear"}, headers=W)
    count("room1", 2, started + 1)
    count("room1", 0, started + 2)  # Lab 2 empties two seconds in
    alert_id = api.get("/api/alerts").json()["alerts"][0]["id"]
    api.post(f"/api/alerts/{alert_id}/ack", headers=W)
    # Hall A's sensor stops: the background check notes it as offline
    store.r.hset("room:room2", "count_ts", started - 10 * main.STALE_S)
    main.background_tick(started + 1)
    end(api)
    listing = api.get("/api/incidents").json()["incidents"]
    rep = api.get(f"/api/incidents/{listing[0]['id']}").json()
    rooms = {r["room_id"]: r for r in rep["rooms"]}
    assert rep["kind"] == "real" and rep["started_by"] == "warden1" and rep["ended_by"] == "warden1"
    assert rep["start_total"] == 7 and rep["duration_s"] >= 0
    assert rooms["room1"]["start_count"] == 5 and rooms["room1"]["to_zero_s"] == 2
    assert rooms["room3"]["empty_at_start"] is True and rooms["room3"]["to_zero_s"] is None
    assert rooms["room2"]["to_zero_s"] is None and rooms["room2"]["status"]["status"] == "clear"
    assert rooms["room2"]["status"]["by"] == "warden1"
    assert [o["room_id"] for o in rep["offline"]] == ["room2"] and rep["offline"][0]["name"] == "Hall A"
    acked = [a for a in rep["alerts"] if a["id"] == alert_id][0]
    assert acked["ack"]["by"] == "warden1"
    assert any(a["subject"].startswith("NADI: Emergency mode ended") for a in rep["alerts"])
    assert len(rep["snapshots"]) >= 1
    assert listing[0]["marked"] == 1 and listing[0]["offline_rooms"] == 1
    ms = api.get(f"/api/incidents/{listing[0]['id']}?lang=ms").json()
    assert any("Mod kecemasan" in a["subject"] for a in ms["alerts"])


def test_people_returning_clears_the_time_to_zero(api):
    now = int(time.time())
    count("room1", 3, now - 5)
    em = start(api)
    count("room1", 0, em["since"] + 1)
    count("room1", 1, em["since"] + 2)  # someone walked back in
    end(api)
    rep = incident.report(api.get("/api/incidents").json()["incidents"][0]["id"])
    room1 = [r for r in rep["rooms"] if r["room_id"] == "room1"][0]
    assert room1["to_zero_s"] is None and room1["end_count"] == 1 and room1["end_at_least"] is False


def test_acknowledging_after_the_end_shows_in_the_report(api):
    em = start(api)
    end(api)
    first = api.get("/api/alerts").json()["alerts"][-1]
    api.post(f"/api/alerts/{first['id']}/ack", headers=W)
    rep = api.get(f"/api/incidents/{em['id']}").json()
    assert [a["ack"]["by"] for a in rep["alerts"] if a["id"] == first["id"]] == ["warden1"]


def test_unknown_or_malformed_report_ids(api):
    assert api.get("/api/incidents/20260101-000000-real-abcd").status_code == 404
    for bad in ("..%2F..%2Fsecrets", "x" * 40, "20260101-000000-real-ABCD"):
        assert api.get(f"/api/incidents/{bad}").status_code == 404
    assert incident.snapshot_file("../etc", "latest", "en") is None
    assert incident.snapshot_file("20260101-000000-real-abcd", "../../x", "en") is None


def test_demo_runs_keep_only_the_last_few_reports(api, monkeypatch):
    for _ in range(incident.DEMO_KEEP + 2):
        main.set_emergency(True, "demo", "demo")
        main.set_emergency(False, "demo", "demo")
        time.sleep(0.001)
    assert len([r for r in incident.reports() if r["demo"]]) == incident.DEMO_KEEP


# --- automatic snapshots ---

def test_snapshot_saved_at_start_then_every_minute(api, tmp_path):
    count("room1", 2)
    em = start(api)
    d = tmp_path / em["id"]
    assert (d / "latest.en.html").is_file() and (d / "latest.ms.html").is_file() and (d / "latest.json").is_file()
    first = sorted(d.glob("snapshot-*.json"))
    assert len(first) == 1
    main.background_tick(em["since"] + 30)
    assert len(sorted(d.glob("snapshot-*.json"))) == 1  # not yet a minute
    main.background_tick(em["since"] + 61)
    assert len(sorted(d.glob("snapshot-*.json"))) == 2
    snap = json.loads((d / "latest.json").read_text(encoding="utf-8"))
    assert snap["id"] == em["id"] and snap["rooms"][0]["name"] == "Lab 2" and snap["emergency_number"] is None
    active = api.get("/api/incidents").json()["active"]
    assert active["id"] == em["id"] and active["snapshots"] == 2
    page = api.get(f"/api/incidents/{em['id']}/snapshot?lang=ms")
    assert page.status_code == 200 and "Nombor kecemasan: 999 (112 dari telefon bimbit)" in page.text
    end(api)
    main.background_tick(em["since"] + 200)
    assert len(sorted(d.glob("snapshot-*.json"))) == 2  # stops when it ends


def test_snapshot_page_escapes_names_and_works_without_a_server(api, monkeypatch, tmp_path):
    monkeypatch.setenv("ROOM_NAMES", "room1:<script>alert(1)</script>")
    monkeypatch.setenv("EMERGENCY_NUMBER", "999 <b>")
    count("room1", 1)
    em = start(api, drill=True)
    html = (tmp_path / em["id"] / "latest.en.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html and "999 &lt;b&gt;" in html
    assert "DRILL: this is a practice run" in html and "Malaysia time" in html
    assert "<link" not in html and "src=" not in html  # nothing to load: it opens from a USB stick


def test_snapshot_failure_does_not_stop_the_alarm(api, monkeypatch, capsys):
    monkeypatch.setattr(incident, "save_snapshot", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    assert start(api)["on"] is True
    assert "snapshot not saved: disk full" in capsys.readouterr().out


def test_emergency_number_setting(api, monkeypatch):
    assert api.get("/api/info").json()["emergency_number"] is None  # the page shows the default in its language
    monkeypatch.setenv("EMERGENCY_NUMBER", "03-1234 5678 (security desk)" + "x" * 50)
    assert len(api.get("/api/info").json()["emergency_number"]) == 40


def test_rescue_order_matches_the_dashboard():
    rooms = [{"room_id": "a", "name": "A", "headcount": 2, "live": True}, {"room_id": "b", "name": "B", "headcount": 0, "live": True},
             {"room_id": "c", "name": "C", "headcount": 2, "live": False}, {"room_id": "d", "name": "D", "headcount": None, "live": False}]
    ranked, zero = incident.rescue_order(rooms)
    assert [r["room_id"] for r in ranked] == ["c", "a", "d"] and [r["room_id"] for r in zero] == ["b"]
