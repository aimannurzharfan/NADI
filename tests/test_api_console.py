"""Endpoints added for the console UI: long-range history, room climate, energy, period comparison, alert
acknowledgement and "am I an admin". No Redis/MySQL needed."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import alerts, logic, main, store
from tests.test_alerts import FakeRedis

TOKEN = {"X-Admin-Token": "console-token-0123456789"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "console-token-0123456789")
    monkeypatch.setenv("ADMIN_TOKENS", "")
    monkeypatch.setattr(main, "_history_cache", {})
    return TestClient(main.app, client=("192.168.1.40", 5000), base_url=LOCAL_URL)


def test_history_buckets_1_min_15_min_1_h():
    assert main.bucket_for(30) == 60 and main.bucket_for(60) == 60
    assert main.bucket_for(180) == 900 and main.bucket_for(24 * 60) == 900
    assert main.bucket_for(7 * 24 * 60) == 3600
    assert main.bucket_for(30 * 24 * 60) == 86400 and main.HISTORY_MAX_MIN == 30 * 24 * 60  # 30 days: one point a day
    assert main.bucket_for(7 * 24 * 60, rooms=50) * 1 > 3600  # many rooms: coarser, never more than MAX_POINTS
    assert 50 * (7 * 24 * 3600 // main.bucket_for(7 * 24 * 60, rooms=50)) <= main.MAX_POINTS


def test_history_range_capped_and_room_checked(api, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "history", lambda since, bucket=None, room_id=None: calls.append((since, bucket, room_id)) or {})
    monkeypatch.setattr(store, "coldest", lambda room_id, since, bucket: {})
    now = time.time()
    out = api.get("/api/history?minutes=999999&room=room1").json()
    since, bucket, room = calls[0]
    assert now - since == pytest.approx(main.HISTORY_MAX_MIN * 60, abs=5) and bucket and room == "room1"
    assert out["bucket_s"] == bucket
    assert api.get("/api/history?room=room99").status_code == 422


def test_room_climate(api, monkeypatch):
    monkeypatch.setattr(store, "climate_history", lambda room, since, bucket=None: [[1, 24.0, 60.0]])
    assert api.get("/api/rooms/room1/climate?minutes=60").json()["points"] == [[1, 24.0, 60.0]]
    assert api.get("/api/rooms/<x>/climate").status_code in (404, 422)


def test_me_says_who_is_admin(api, monkeypatch):
    assert api.get("/api/me").json()["admin"] is False
    me = api.get("/api/me", headers=TOKEN).json()
    assert (me["admin"], me["who"], me["rule"], me["viewer"], me["viewer_required"]) == (True, "admin", "token", True, False)
    monkeypatch.setenv("ADMIN_TOKEN", "")
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    assert local.get("/api/me").json()["admin"] is True  # the server computer, no token needed
    assert api.get("/api/me").json()["admin"] is False


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(store, "r", fake)
    return fake


def test_acknowledge_is_shared_and_admin_only(api, fake_redis):
    alerts.send("waste", "alert.waste_subject", "alert.waste_body", name="Lab 2", minutes=12, temp="22.0", rm="0.40")
    alert = api.get("/api/alerts").json()["alerts"][0]
    assert alert["severity"] == "warning" and alert["ack"] is None
    assert api.post(f"/api/alerts/{alert['id']}/ack").status_code == 401
    assert api.post(f"/api/alerts/{alert['id']}/ack", headers=TOKEN).json()["by"] == "admin"
    seen = api.get("/api/alerts").json()["alerts"][0]["ack"]  # any other screen sees it too
    assert seen["by"] == "admin" and seen["ts"] > 0
    assert api.post("/api/alerts/abcdef-000000/ack", headers=TOKEN).status_code == 404


def test_degree_sign_is_utf8_from_the_strings_file_to_the_response(api):
    """The waste alert's "23.6 °C" leaves the server as UTF-8 bytes (C2 B0), in both languages, after a trip through
    the alert store. (A tool that reads the JSON as Latin-1 shows the same bytes as "Â°".)"""
    alerts.send("waste", "alert.waste_subject", "alert.waste_body", name="Lab 2", minutes=12, temp="23.6", rm="0.40")
    for url in ("/api/alerts", "/api/alerts?lang=ms", "/api/rooms", "/api/rooms?lang=ms"):
        res = api.get(url)
        assert res.status_code == 200 and res.headers["content-type"].startswith("application/json")
        assert b"23.6\xc2\xa0\xc2\xb0C" in res.content and b"\xc3\x82" not in res.content, url
        assert "23.6 °C" in json.dumps(res.json(), ensure_ascii=False)


def test_old_alerts_without_id_get_a_stable_one(fake_redis):
    fake_redis.lpush("alerts", json.dumps({"ts": 1, "subject": "NADI: old", "message": "old text", "via": "console"}))
    first, second = alerts.recent()[0]["id"], alerts.recent()[0]["id"]
    assert first == second and len(first) == 12


def test_energy_maths(api, monkeypatch):
    monkeypatch.setattr(main, "refresh_live", lambda now, lang=None: None)
    monkeypatch.setattr(main, "_last", {**main._last, "rooms": []})
    monkeypatch.setattr(store, "waste_day", lambda now, days_ago=0, room_id=None: (1.0 if room_id == "room1" else 0.0)
                        if room_id else 2.0)
    out = api.get("/api/energy").json()
    assert out["today"]["rm"] == 2.0 and out["week"]["rm"] == 14.0 and out["previous_week"]["rm"] == 14.0
    assert out["today"]["kwh"] == pytest.approx(2.0 / logic.TARIFF_RM_PER_KWH, abs=0.1)
    assert out["today"]["co2_kg"] == pytest.approx(out["today"]["kwh"] * main.CO2_KG_PER_KWH, abs=0.2)
    room1 = next(r for r in out["by_room"] if r["room_id"] == "room1")
    assert room1["rm_today"] == 1.0 and room1["rm_week"] == 7.0
    assert len(out["daily"]) == 7


def test_summary_compares_with_the_previous_period(api, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(store, "history", lambda since, bucket=None, room_id=None: {
        "room1": [[now - 30 * 60, 2.0], [now - 90 * 60, 1.0]], "room2": [[now - 30 * 60, 1.0]]})
    monkeypatch.setattr(alerts, "recent", lambda lang="en", limit=20: [{"ts": now - 60}, {"ts": now - 4000}, {"ts": now - 5000}])
    out = api.get("/api/summary?minutes=60").json()
    assert out["people_avg"] == 3.0 and out["people_avg_prev"] == 1.0
    assert out["alerts"] == 1 and out["alerts_prev"] == 2
