"""Health endpoint and input-validation fixes in ingest/iotda_push/mqtt_local. No Redis/MySQL/MQTT needed."""
import json
import time

import pytest

from server import main, mqtt_local
from tests.util import local_request


# --- ingest: bad ts, non-dict services, non-list services ---

@pytest.fixture
def stub_store(monkeypatch):
    saved = []
    monkeypatch.setattr(main.store, "save_csi", lambda room, ts, count, p: saved.append(("csi", room, ts)))
    monkeypatch.setattr(main.store, "save_climate", lambda room, ts, p: saved.append(("climate", room, ts)))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    return saved


def csi(room="room1", **props):
    return {"service_id": "csi", "properties": {"room_id": room, "motion_std": 0.1, **props}}


def test_bad_ts_rejects_the_report(stub_store):
    for bad_ts in ("not-a-number", "1761800000", {"x": 1}, [1, 2], float("nan"), float("inf"), True):
        assert main.ingest([csi(ts=bad_ts)]) == 0
    assert stub_store == []


def test_valid_ts_kept(stub_store):
    now = int(time.time())
    main.ingest([csi("room1", ts=now)])
    main.ingest([csi("room2", ts=now + 0.9)])
    assert [s[2] for s in stub_store] == [now, now]


def test_missing_or_zero_ts_uses_server_clock(stub_store):
    now = time.time()
    main.ingest([csi("room1")])
    main.ingest([csi("room2", ts=0)])
    assert len(stub_store) == 2 and all(s[2] >= int(now) for s in stub_store)


def test_non_dict_service_entry_rejects_the_report(stub_store):
    assert main.ingest(["garbage", 42, None, [1, 2], csi(ts=0)]) == 0
    assert stub_store == []


def test_non_list_services_yields_zero(stub_store):
    for bad in ("not-a-list", 42, None, {"services": []}, []):
        assert main.ingest(bad) == 0
    assert stub_store == []


def test_one_bad_service_rejects_the_whole_batch(stub_store):
    assert main.ingest([csi("room1", ts={"bad": "type"}), csi("room2", ts=0)]) == 0
    assert stub_store == []


# --- iotda_push: non-dict notify_data / body ---

@pytest.fixture
def stub_iotda(monkeypatch, stub_store):
    monkeypatch.setattr(main, "INGEST_TOKEN", "")
    pushed = []
    monkeypatch.setattr(main.store, "mark_iotda_push", lambda ts: pushed.append(ts))
    return pushed


def push(notify_data):
    return main.iotda_push({"resource": "device.property", "notify_data": notify_data}, local_request())


def test_iotda_push_non_dict_parts_get_422(stub_iotda):
    from fastapi import HTTPException
    for bad in ("a-string", ["a", "list"], 42, None, True, {"body": "not-a-dict"},
                {"header": "not-a-dict", "body": {"services": []}}):
        with pytest.raises(HTTPException) as exc:
            push(bad)
        assert exc.value.status_code == 422
    assert stub_iotda == []


def test_iotda_push_sim_local_not_marked(stub_iotda):
    assert push({"header": {"device_id": "sim-local"}, "body": {"services": [csi(ts=0)]}})["saved"] == 1
    assert stub_iotda == []


def test_iotda_push_ignores_non_property_resource(stub_iotda):
    res = main.iotda_push({"resource": "device.command"}, local_request())
    assert res == {"ok": True, "ignored": "device.command"}
    assert stub_iotda == []


def test_iotda_push_valid_body(stub_iotda, stub_store):
    res = push({"header": {"device_id": "dev1"}, "body": {"services": [csi(ts=0)]}})
    assert res == {"ok": True, "saved": 1, "duplicate": 0, "dropped": 0, "suspicious": 0}
    assert stub_store[0][:2] == ("csi", "room1")
    assert len(stub_iotda) == 1


def test_iotda_push_bad_token_rejected(monkeypatch):
    monkeypatch.setattr(main, "INGEST_TOKEN", "s3cret")
    monkeypatch.setattr(main.store, "mark_iotda_push", lambda ts: None)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        main.iotda_push({"resource": "device.property"}, local_request(), token="wrong")
    assert exc.value.status_code == 401


# --- mqtt_local: non-dict JSON payload ---

def test_services_from_payload_dict_with_services():
    payload = json.dumps({"services": [{"service_id": "csi"}]}).encode()
    assert mqtt_local.services_from_payload(payload) == [{"service_id": "csi"}]


def test_services_from_payload_missing_services():
    assert mqtt_local.services_from_payload(json.dumps({"room_id": "r1"}).encode()) == []


def test_services_from_payload_empty_services():
    assert mqtt_local.services_from_payload(json.dumps({"services": []}).encode()) == []


def test_services_from_payload_non_object_json():
    assert mqtt_local.services_from_payload(json.dumps([1, 2, 3]).encode()) == []
    assert mqtt_local.services_from_payload(b"42") == []
    assert mqtt_local.services_from_payload(b'"hello"') == []
    assert mqtt_local.services_from_payload(b"true") == []
    assert mqtt_local.services_from_payload(b"null") == []


def test_services_from_payload_bad_json_raises():
    with pytest.raises(Exception):
        mqtt_local.services_from_payload(b"not json at all")


def test_services_from_payload_non_list_services_passed_through():
    assert mqtt_local.services_from_payload(json.dumps({"services": "x"}).encode()) == "x"


# --- /api/health endpoint ---

@pytest.fixture
def stub_checks(monkeypatch):
    state = {"redis": True, "mysql": True, "mqtt": True}
    monkeypatch.setattr(main, "_check_redis", lambda: state["redis"])
    monkeypatch.setattr(main, "_check_mysql", lambda: state["mysql"])
    monkeypatch.setattr(main, "_check_mqtt", lambda: state["mqtt"])
    return state


def test_health_all_up(stub_checks, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    assert main.api_health() == {"status": "ok", "mode": "local",
                                 "redis": True, "mysql": True, "mqtt": True}


def test_health_one_down(stub_checks, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    stub_checks["mysql"] = False
    assert main.api_health() == {"status": "degraded", "mode": "local",
                                 "redis": True, "mysql": False, "mqtt": True}


def test_health_all_down(stub_checks, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "huawei")
    stub_checks["redis"] = stub_checks["mysql"] = stub_checks["mqtt"] = False
    assert main.api_health() == {"status": "degraded", "mode": "huawei",
                                 "redis": False, "mysql": False, "mqtt": False}


def test_health_keys_and_no_secrets(stub_checks, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("REDIS_PASSWORD", "super-secret")
    monkeypatch.setenv("MYSQL_PASSWORD", "db-secret")
    monkeypatch.setenv("MQTT_SERVER_PASSWORD", "mqtt-secret")
    res = main.api_health()
    assert set(res) == {"status", "mode", "redis", "mysql", "mqtt"}
    body = json.dumps(res)
    for secret in ("super-secret", "db-secret", "mqtt-secret"):
        assert secret not in body


def test_health_check_timeout_returns_false(monkeypatch):
    def slow():
        time.sleep(5)
        return True
    monkeypatch.setattr(main, "_check_redis", slow)
    monkeypatch.setattr(main, "_check_mysql", lambda: True)
    monkeypatch.setattr(main, "_check_mqtt", lambda: True)
    monkeypatch.setenv("NADI_MODE", "local")
    res = main.api_health()
    assert res["redis"] is False
    assert res["status"] == "degraded"


def test_health_check_exception_returns_false(monkeypatch):
    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(main, "_check_redis", boom)
    monkeypatch.setattr(main, "_check_mysql", lambda: True)
    monkeypatch.setattr(main, "_check_mqtt", lambda: True)
    monkeypatch.setenv("NADI_MODE", "local")
    res = main.api_health()
    assert res["redis"] is False
    assert res["mysql"] is True and res["mqtt"] is True


def test_health_returns_bools(stub_checks, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    res = main.api_health()
    assert all(isinstance(res[k], bool) for k in ("redis", "mysql", "mqtt"))
