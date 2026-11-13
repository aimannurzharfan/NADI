"""Board health in reports, the device list for the Sensors page, and the board address for "setup". No services needed."""
import time

import pytest
from fastapi.testclient import TestClient

from tests.util import LOCAL_URL

from server import main, store, validate


def csi(**props):
    return {"service_id": "csi", "properties": {"room_id": "room1", "ts": 0, "motion_std": 0.1, **props}}


HEALTH = {"fw_version": "1.1.0", "uptime_s": 3600, "wifi_rssi": -55, "free_heap": 180000, "dropped": 2}


def test_health_fields_checked_and_kept():
    clean = validate.check(csi(**HEALTH))
    assert clean["properties"]["health"] == HEALTH


def test_reports_without_health_still_accepted():
    assert validate.check(csi())["properties"]["health"] == {}  # boards on older firmware keep working


@pytest.mark.parametrize("field,value", [
    ("fw_version", "<script>"), ("fw_version", "x" * 17), ("fw_version", 1.1), ("wifi_rssi", 20),
    ("uptime_s", -1), ("free_heap", float("nan")), ("dropped", "3"),
])
def test_bad_health_rejected(field, value):
    with pytest.raises(validate.Rejected):
        validate.check(csi(**{**HEALTH, field: value}))


@pytest.fixture
def saved(monkeypatch):
    rows, devices = [], []
    monkeypatch.setattr(store, "save_csi", lambda room, ts, count, p: rows.append(p))
    monkeypatch.setattr(store, "save_device", lambda *a: devices.append(a))
    monkeypatch.setattr(main, "check_waste", lambda room, now: None)
    return rows, devices


def test_health_stored_per_device_not_in_history(saved):
    rows, devices = saved
    main.process([csi(**HEALTH)], "nadi-recv-1")
    assert "health" not in rows[0] and "fw_version" not in rows[0]  # history table gets readings only
    device_id, service, room, ts, health = devices[0]
    assert (device_id, service, room, health) == ("nadi-recv-1", "csi", "room1", HEALTH)
    main.process([csi(**HEALTH)], None)  # no trusted device name: nothing to file it under
    assert len(devices) == 1


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    monkeypatch.setenv("ADMIN_TOKEN", "board-token-0123456789")
    monkeypatch.setenv("ADMIN_TOKENS", "")
    return TestClient(main.app, client=("192.168.1.30", 5000), base_url=LOCAL_URL)


def test_device_list_marks_online_by_interval(api, monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(store, "devices", lambda: [
        {"device_id": "nadi-recv-1", "service": "csi", "room_id": "room1", "last_seen": now - 30, **HEALTH},
        {"device_id": "nadi-recv-2", "service": "csi", "room_id": "room2", "last_seen": now - 3 * main.REPORT_INTERVAL_S - 5, **HEALTH},
        {"device_id": "nadi-climate-1", "service": "climate", "room_id": "room1", "last_seen": now - 150, **HEALTH},
    ])
    assert api.get("/api/devices").status_code == 401  # admin only
    devices = {d["device_id"]: d for d in api.get("/api/devices", headers={"X-Admin-Token": "board-token-0123456789"}).json()["devices"]}
    assert devices["nadi-recv-1"]["online"] and not devices["nadi-recv-2"]["online"]
    assert devices["nadi-climate-1"]["online"]  # climate reports once a minute, so 150 s is still fine
    assert devices["nadi-recv-1"]["fw_version"] == "1.1.0" and devices["nadi-recv-1"]["wifi_rssi"] == -55


def test_board_address_is_admin_only_and_flags_a_changed_ip(api, monkeypatch):
    monkeypatch.setattr(main, "lan_ip", lambda: "192.168.43.20")
    monkeypatch.setenv("MQTT_LAN_IP", "192.168.1.50")
    assert api.get("/api/board-setup").status_code == 401
    out = api.get("/api/board-setup", headers={"X-Admin-Token": "board-token-0123456789"}).json()
    assert out == {"ip": "192.168.43.20", "port": 1883, "configured_ip": "192.168.1.50", "mismatch": True}
    monkeypatch.setenv("MQTT_LAN_IP", "192.168.43.20")
    assert api.get("/api/board-setup", headers={"X-Admin-Token": "board-token-0123456789"}).json()["mismatch"] is False


def test_board_address_not_offered_in_huawei_mode(api, monkeypatch):
    monkeypatch.setenv("NADI_MODE", "huawei")
    assert api.get("/api/board-setup", headers={"X-Admin-Token": "board-token-0123456789"}).status_code == 409
