"""Bad input, abuse, many users and broken dependencies. No Redis/MySQL/MQTT/Ollama needed: those are faked.
The same attacks run against a live server in scripts/stress/attack.py."""
import json
import socket
import threading
import time

import pymysql
import pytest
import redis
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import chat, guard, health, main, store, validate

NOW = int(time.time())


def csi(room="room1", **props):
    return {"service_id": "csi", "properties": {"room_id": room, "motion_std": 0.1, **props}}


def reason(svc, device_id=None):
    try:
        validate.check(svc, device_id)
        return None
    except validate.Rejected as e:
        return e.reason


# --- input checks ---

@pytest.mark.parametrize("room", [
    "room1' OR '1'='1", "room1; DROP TABLE occupancy;--", "<script>alert(1)</script>", "<img src=x onerror=alert(1)>",
    "", " room1", "room1\n", "bilik😀", "x" * 33, 42, None, ["room1"],
])
def test_bad_room_ids_rejected(room):
    assert reason(csi(room, ts=0)) == "api.reject_room_id"


def test_unknown_room_rejected(monkeypatch):
    monkeypatch.delenv("ROOM_NAMES", raising=False)
    assert reason(csi("room99", ts=0)) == "api.reject_unknown_room"
    monkeypatch.setenv("ROOM_NAMES", "room99:Store")
    assert reason(csi("room99", ts=0)) is None  # named in ROOM_NAMES = known


@pytest.mark.parametrize("field,value,why", [
    ("motion_std", float("nan"), "api.reject_range"), ("motion_std", float("inf"), "api.reject_range"),
    ("motion_std", -1, "api.reject_range"), ("motion_std", 1e9, "api.reject_range"),
    ("motion_std", "0.5", "api.reject_type"), ("motion_std", True, "api.reject_type"),
    ("motion_std", None, "api.reject_missing"), ("rssi_mean", 20, "api.reject_range"),
    ("n_packets", -5, "api.reject_range"), ("amp_var", float("-inf"), "api.reject_range"),
])
def test_bad_csi_numbers_rejected(field, value, why):
    assert reason(csi(ts=0, **{field: value})) == why


@pytest.mark.parametrize("temp,why", [(500, "api.reject_range"), (-100, "api.reject_range"),
                                      (float("nan"), "api.reject_range"), ("hot", "api.reject_type")])
def test_bad_temperatures_rejected(temp, why):
    assert reason({"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": temp}}) == why


def test_humidity_bounds():
    ok = {"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": 24.0, "humidity": 60}}
    assert reason(ok) is None
    ok["properties"]["humidity"] = 140
    assert reason(ok) == "api.reject_range"


def test_timestamps():
    assert reason(csi(ts=NOW - 2 * 86400)) == "api.reject_ts_old"
    assert reason(csi(ts=NOW + 3600)) == "api.reject_ts_future"
    assert reason(csi(ts=1)) == "api.reject_ts_old"
    assert reason(csi(ts=NOW - 30)) is None
    assert validate.check(csi(ts=0))["ts"] >= NOW  # firmware without NTP sends 0


def test_unknown_service_and_extra_fields():
    assert reason({"service_id": "headcount", "properties": {"room_id": "room1", "people": 9999}}) == "api.reject_service"
    clean = validate.check(csi(ts=0, headcount=9999, mac="aa:bb:cc:dd:ee:ff"))
    assert "headcount" not in clean["properties"] and "mac" not in clean["properties"]  # only checked fields stored


def test_device_rooms(monkeypatch):
    monkeypatch.setenv("DEVICE_ROOMS", "nadi-recv-1:room1,nadi-sim:*")
    assert reason(csi("room1", ts=0), "nadi-recv-1") is None
    assert reason(csi("room2", ts=0), "nadi-recv-1") == "api.reject_device_room"
    assert reason(csi("room2", ts=0), "nadi-sim") is None
    assert reason(csi("room1", ts=0), "nadi-unknown") == "api.reject_device_room"
    monkeypatch.setenv("DEVICE_ROOMS", "")
    assert reason(csi("room2", ts=0), "anyone") is None


def test_report_limits():
    assert validate.check_all([csi(ts=0)] * 51)[1]
    assert validate.check_all([])[1]


@pytest.fixture
def saved(monkeypatch):
    rows = []
    monkeypatch.setattr(store, "save_csi", lambda room, ts, count, p: rows.append(("csi", room, ts, count)))
    monkeypatch.setattr(store, "save_climate", lambda room, ts, p: rows.append(("climate", room, ts, p)))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    return rows


def test_model_output_clamped(saved, monkeypatch):
    monkeypatch.setattr(main.model, "headcount", lambda p: (9999, "mindspore"))
    main.ingest([csi(ts=0)])
    assert saved[0][3] == 3


def test_duplicates_counted_not_saved(monkeypatch):
    monkeypatch.setattr(main.model, "headcount", lambda p: (1, "threshold"))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    seen = set()
    monkeypatch.setattr(store, "save_csi", lambda room, ts, count, p: (room, ts) not in seen and not seen.add((room, ts)))
    report = [csi(ts=NOW)]
    assert main.process(report) == {"saved": 1, "duplicate": 0, "dropped": 0, "suspicious": 0, "errors": []}
    assert main.process(report) == {"saved": 0, "duplicate": 1, "dropped": 0, "suspicious": 0, "errors": []}


# --- HTTP: sizes, malformed bodies, clean 4xx ---

@pytest.fixture
def api(monkeypatch, saved):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "")
    monkeypatch.setenv("ADMIN_TOKENS", "warden1:tok-one-0123456789,warden2:tok-two-0123456789")
    monkeypatch.setenv("OLLAMA_MODEL", "")
    monkeypatch.setattr(main, "INGEST_TOKEN", "")
    monkeypatch.setattr(store, "rooms", lambda: [])
    monkeypatch.setattr(store, "mark_iotda_push", lambda ts: None)
    monkeypatch.setattr(store, "waste_today", lambda now: 0.0)
    monkeypatch.setattr(main.alerts, "recent", lambda lang="en": [])
    return TestClient(main.app, client=("10.0.0.5", 5000), base_url=LOCAL_URL)


@pytest.fixture
def local(api):
    """The server computer itself: without INGEST_TOKEN only it may post to /iotda (sim/fake_sensor.py --local)."""
    return TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)


W1 = {"X-Admin-Token": "tok-one-0123456789"}


def test_oversized_bodies_get_413(api):
    big = json.dumps({"question": "x" * 5000})
    assert api.post("/api/chat", content=big, headers={**W1, "Content-Type": "application/json"}).status_code == 413
    body = {"resource": "device.property", "notify_data": {"body": {"services": [csi(ts=0, pad="x" * 9000)]}}}
    assert api.post("/iotda", json=body).status_code == 413

    def chunks():  # no Content-Length: the limit still holds
        for _ in range(10):
            yield b"x" * 1000
    assert api.post("/api/chat", content=chunks(), headers=W1).status_code == 413


def test_malformed_and_wrong_types_never_500(api, local):
    for body in (b"{not json", b"", b"[1,2,3]", b'"text"', b"null", b'{"on": NaN}'):
        assert api.post("/api/emergency", content=body, headers={**W1, "Content-Type": "application/json"}).status_code == 422
    assert api.post("/api/emergency", json={"on": "false"}, headers=W1).status_code == 422  # text must not start it
    assert api.post("/api/emergency", json={"on": 1}, headers=W1).status_code == 422
    assert api.post("/api/chat", json={"question": ["a"]}, headers=W1).status_code == 422
    nan_body = b'{"resource":"device.property","notify_data":{"body":{"services":[{"service_id":"csi",' \
               b'"properties":{"room_id":"room1","ts":0,"motion_std":NaN}}]}}}'
    res = local.post("/iotda", content=nan_body, headers={"Content-Type": "application/json"})
    assert res.status_code == 422 and "motion_std" in json.dumps(res.json())


def test_iotda_rejects_bad_reports_cleanly(local, saved):
    def push(services):
        return local.post("/iotda", json={"resource": "device.property", "notify_data": {"body": {"services": services}}})
    for bad in ([csi("<script>", ts=0)], [csi("room1", ts=NOW + 9999)], [csi("room1", ts=0, motion_std=9999)],
                [{"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": 500}}],
                [csi("room99", ts=0)], "x", None):
        res = push(bad)
        assert res.status_code == 422, bad
    assert saved == []
    assert push([csi(ts=0)]).json()["saved"] == 1


def test_chat_question_limits(api):
    assert api.post("/api/chat", json={"question": "q" * 501}, headers=W1).status_code == 422
    assert api.post("/api/chat", json={"question": "   "}, headers=W1).status_code == 400
    for q in ("Berapa orang di dalam? 😀🔥", "<script>alert(1)</script>", "'; DROP TABLE occupancy;--", "q" * 500):
        res = api.post("/api/chat", json={"question": q}, headers=W1)
        assert res.status_code == 200
        assert "<script>" not in res.json()["answer"]  # answers are built from rules, never echo the question


# --- abuse: lockout, rate limits, two wardens at once ---

def test_admin_token_brute_force_locks_ip(api):
    for i in range(guard.FAIL_LIMIT):
        assert api.post("/api/chat", json={"question": "hi"}, headers={"X-Admin-Token": f"guess{i}"}).status_code == 401
    res = api.post("/api/chat", json={"question": "hi"}, headers={"X-Admin-Token": "guess-again"})
    assert res.status_code == 429 and int(res.headers["Retry-After"]) > 60  # more guesses refused
    # someone sharing the IP cannot lock a warden out: the right token still works
    assert api.post("/api/chat", json={"question": "hi"}, headers=W1).status_code == 200


def test_only_short_tokens_fail_closed(api, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "")
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    local = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    res = local.post("/api/chat", json={"question": "hi"})
    assert res.status_code == 503 and "16" in res.json()["detail"]  # not the localhost fallback
    assert local.post("/api/emergency", json={"on": True}, headers={"X-Admin-Token": "short"}).status_code == 503
    assert main.admin_rule() == "token"


def test_short_tokens_ignored(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    monkeypatch.setenv("ADMIN_TOKENS", "w1:also-short,w2:long-enough-token-123")
    assert main.admin_tokens() == {"long-enough-token-123": "w2"}


def test_iotda_device_claim_needs_ingest_token(api, local, monkeypatch, saved):
    monkeypatch.setenv("DEVICE_ROOMS", "nadi-recv-1:room1")
    body = {"resource": "device.property",
            "notify_data": {"header": {"device_id": "nadi-recv-1"}, "body": {"services": [csi(ts=0)]}}}
    assert api.post("/iotda", json=body).status_code == 401  # no token: only this computer may post at all
    assert local.post("/iotda", json=body).status_code == 422  # no token: the device claim is not trusted
    monkeypatch.setattr(main, "INGEST_TOKEN", "ingest-secret")
    assert api.post("/iotda?token=ingest-secret", json=body).json()["saved"] == 1


def test_limiter_clock_starts_every_test_on_a_whole_minute(limiter_clock, monkeypatch):
    # the limiter counts in fixed minutes: a count test must never run across the end of one
    assert guard.time is limiter_clock and guard.time.time() % 60 < 30
    # even when the real clock is one tick from the next minute, the limiter stays in one window
    real = time.time
    edge = (real() // 60 + 1) * 60 - 0.001
    monkeypatch.setattr(time, "time", lambda: edge)
    moved = type(limiter_clock)()
    monkeypatch.setattr(guard, "time", moved)
    first = guard.allow("chat", "10.9.9.9", 2)             # the real clock: the last tick of a minute
    monkeypatch.setattr(time, "time", lambda: edge + 0.5)  # the real minute has turned
    assert [first, guard.allow("chat", "10.9.9.9", 2), guard.allow("chat", "10.9.9.9", 2)[0]] == [(True, 0), (True, 0), False]


def test_chat_flood_rate_limited(api):
    codes = [api.post("/api/chat", json={"question": "How many people?"}, headers=W1).status_code for _ in range(15)]
    assert codes[:guard.CHAT_PER_MIN] == [200] * guard.CHAT_PER_MIN and set(codes[guard.CHAT_PER_MIN:]) == {429}


@pytest.fixture
def fake_redis():
    return store.r  # conftest gives every test an empty fakeredis


def test_two_wardens_start_and_end_at_the_same_moment(api, fake_redis, monkeypatch):
    sent = []
    monkeypatch.setattr(main.alerts, "send", lambda kind, s, b, **v: sent.append((kind, s)))

    def together(n, press):
        barrier, results = threading.Barrier(n), []

        def run(i):
            barrier.wait()
            results.append(press(i))
        threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return results

    def start(i):
        c = TestClient(main.app, client=(f"10.0.1.{i}", 5000), base_url=LOCAL_URL)
        return c.post("/api/emergency", json={"on": True}, headers={"X-Admin-Token": ("tok-one-0123456789", "tok-two-0123456789")[i % 2]}).json()
    results = together(8, start)
    assert len({r["since"] for r in results}) == 1 and all(r["on"] for r in results)  # one alarm time
    assert [s for k, s in sent if k == "emergency"] == ["alert.emergency_subject"]  # one alarm alert
    assert sum(1 for _, s in sent if s == "alert.audit_start_subject") == 1

    def end(i):
        return TestClient(main.app, client=(f"10.0.2.{i}", 5000), base_url=LOCAL_URL).post("/api/emergency", json={"on": False}, headers=W1).json()
    assert all(r["on"] is False and r["since"] is None for r in together(8, end))
    assert sum(1 for _, s in sent if s == "alert.audit_end_subject") == 1
    log = store.audit_log()
    assert [e["action"] for e in log] == ["end", "start"]
    assert log[1]["by"] in ("warden1", "warden2") and log[1]["ip"].startswith("10.0.1.")


def test_public_alert_has_no_ip_audit_log_is_admin_only(api, fake_redis, monkeypatch):
    sent = []
    monkeypatch.setattr(main.alerts, "send", lambda kind, s, b, **v: sent.append((s, v)))
    api.post("/api/emergency", json={"on": True}, headers=W1)
    audit = [v for s, v in sent if s == "alert.audit_start_subject"][0]
    assert audit.keys() == {"who", "time", "drill"} and audit["who"] == "warden1" and audit["drill"] is False
    assert api.get("/api/audit").status_code == 401  # the token is set, so no token = refused
    log = api.get("/api/audit", headers=W1).json()["audit"]
    assert log[0]["ip"] == "10.0.0.5" and log[0]["by"] == "warden1"


def test_emergency_toggle_spam_rate_limited(api, fake_redis, monkeypatch):
    monkeypatch.setattr(main.alerts, "send", lambda *a, **k: "console")
    codes = [api.post("/api/emergency", json={"on": i % 2 == 0}, headers=W1).status_code for i in range(10)]
    assert codes.count(200) == guard.EMERGENCY_PER_MIN and set(codes[guard.EMERGENCY_PER_MIN:]) == {429}


# --- broken dependencies ---

def test_chat_skips_ollama_known_to_be_down(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: False)
    monkeypatch.setattr(chat, "llm_answer", lambda *a: pytest.fail("model called while down"))
    rooms = [{"room_id": "room1", "name": "room1", "headcount": 0, "temp_c": 24.0, "live": True, "waste": None}]
    assert chat.answer("How many people inside?", {"now": 0, "emergency": {"on": False}, "rooms": rooms})["source"] == "fallback"


def test_rooms_survive_redis_going_down(api, monkeypatch):
    rows = [{"room_id": "room1", "headcount": 2, "count_ts": int(time.time()), "temp_c": 24.0, "humidity": 60.0,
             "empty_cold_since": None, "waste_alert_ts": None}]
    monkeypatch.setattr(store, "rooms", lambda: rows)
    monkeypatch.setattr(store, "emergency", lambda: {"on": True, "since": 123})
    first = api.get("/api/rooms").json()
    assert first["stale_ts"] is None and first["offline"] == {}

    def down():
        raise redis.ConnectionError("refused")
    monkeypatch.setattr(store, "rooms", down)
    res = api.get("/api/rooms")
    assert res.status_code == 200
    body = res.json()
    assert body["stale_ts"] == first["now"] and "redis" in body["offline"]
    assert body["rooms"][0]["headcount"] == 2 and body["emergency"] == {"on": True, "since": 123}  # last known kept
    assert body["rooms"][0]["live"] is False  # shown as "last known count", not live

    monkeypatch.setattr(store, "rooms", lambda: rows)
    monkeypatch.setattr(health, "RETRY_S", 0)
    assert api.get("/api/rooms").json()["offline"] == {}  # back on its own


def test_write_endpoints_give_503_not_500_when_redis_is_down(api, monkeypatch):
    def down(*a, **k):
        raise redis.ConnectionError("refused")
    monkeypatch.setattr(store, "start_emergency", down)
    res = api.post("/api/emergency", json={"on": True}, headers=W1)
    assert res.status_code == 503 and "Redis" in res.json()["detail"]


def test_history_rows_buffered_while_mysql_is_down(monkeypatch):
    executed, up = [], {"ok": False}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def cursor(self):
            return self

        def execute(self, sql, params):
            executed.append(params)

    def connect():
        if not up["ok"]:
            raise pymysql.err.OperationalError(2003, "refused")
        return Conn()
    monkeypatch.setattr(store, "mysql", connect)
    monkeypatch.setattr(health, "RETRY_S", 0)
    store._buffer.clear()
    for i in range(3):
        store._write(store.INSERT_CLIMATE, ("room1", i, 24.0, 60.0))
    assert store.buffered() == 3 and executed == [] and not health.ok("mysql")
    up["ok"] = True
    store._write(store.INSERT_CLIMATE, ("room1", 3, 24.0, 60.0))
    assert [p[1] for p in executed] == [3, 0, 1, 2] and store.buffered() == 0 and health.ok("mysql")


def test_old_nan_in_redis_does_not_break_json():
    assert store._num({"temp_c": "nan"}, "temp_c", float) is None
    assert store._num({"temp_c": "inf"}, "temp_c", float) is None
    assert store._num({"temp_c": "24.5"}, "temp_c", float) == 24.5


def test_slow_model_times_out_at_5_s_and_falls_back(monkeypatch):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    held = []
    threading.Thread(target=lambda: held.append(srv.accept()), daemon=True).start()  # accepts, never answers
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{srv.getsockname()[1]}/v1")
    monkeypatch.setattr(chat, "ollama_up", lambda max_age_s=30: True)  # Ollama is up, just too slow to answer
    rooms = [{"room_id": "room1", "name": "room1", "headcount": 2, "temp_c": 24.0, "live": True, "waste": None}]
    start = time.time()
    out = chat.answer("How many people inside?", {"now": 0, "emergency": {"on": False}, "rooms": rooms})
    took = time.time() - start
    srv.close()
    assert chat.TIMEOUT_S == 5
    assert out["source"] == "fallback" and out["answer"] == "Whole building: 2 people inside, in 1 room."
    assert 4.5 <= took < 6.5


def test_mqtt_device_reporting_for_another_room_is_refused(monkeypatch, saved):
    """Through the real MQTT message handler: topic device ID + DEVICE_ROOMS decide which rooms it may report."""
    from server import mqtt_local

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return lambda *a, **k: None
    monkeypatch.setattr(mqtt_local.mqtt, "Client", FakeClient)
    monkeypatch.setenv("MQTT_DEVICE_IDS", "nadi-recv-1,nadi-recv-2")
    monkeypatch.setenv("DEVICE_ROOMS", "nadi-recv-1:room1,nadi-recv-2:room2")
    client = mqtt_local.start(main.ingest)

    class Msg:
        def __init__(self, device, room):
            self.topic = f"$oc/devices/{device}/sys/properties/report"
            self.payload = json.dumps({"services": [csi(room, ts=0)]}).encode()
    client.on_message(client, None, Msg("nadi-recv-1", "room2"))  # board 1 claiming board 2's room
    client.on_message(client, None, Msg("nadi-other", "room1"))  # not an allowed device at all
    assert saved == []
    client.on_message(client, None, Msg("nadi-recv-1", "room1"))
    assert [r[1] for r in saved] == ["room1"]


def test_bad_history_row_is_dropped_not_retried_forever(monkeypatch):
    executed = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def cursor(self):
            return self

        def execute(self, sql, params):
            if params[0] == "bad":
                raise pymysql.err.DataError(1406, "Data too long for column 'source'")
            executed.append(params[0])
    monkeypatch.setattr(store, "mysql", lambda: Conn())
    store._buffer.clear()
    store._buffer.extend([(store.INSERT_CLIMATE, ("a",)), (store.INSERT_CLIMATE, ("bad",)), (store.INSERT_CLIMATE, ("b",))])
    store.flush_buffer()
    assert executed == ["a", "b"] and store.buffered() == 0 and health.ok("mysql")  # bad row dropped, rest written
    store._write(store.INSERT_CLIMATE, ("bad",))
    assert store.buffered() == 0 and health.ok("mysql")  # not queued, MySQL not marked offline


def test_device_id_stored_at_most_64_characters(monkeypatch, saved):
    seen = []
    monkeypatch.setattr(store, "save_csi", lambda room, ts, count, p: seen.append(p["source"]))
    main.process([csi(ts=0)], "d" * 200)
    assert seen == ["d" * 64]
