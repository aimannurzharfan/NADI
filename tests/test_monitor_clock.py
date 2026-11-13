"""Sensor stopped / back online alerts, the NTP clock check and Malaysia time."""
import socket
import struct
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import alerts, clock, main, monitor, store, timeutil
from tests.util import LOCAL_URL


@pytest.fixture
def devices(monkeypatch):
    monkeypatch.setenv("ROOM_NAMES", "room1:Lab 2,room2:Hall A")
    state = []
    monkeypatch.setattr(store, "devices", lambda: [dict(d) for d in state])
    return state


def dev(device_id, service, last_seen, rooms):
    return {"device_id": device_id, "service": service, "last_seen": last_seen, "rooms": rooms, "room_id": rooms[0]}


def kept():
    return alerts.recent(limit=alerts.KEEP)


def test_one_alert_when_a_sensor_stops_and_one_when_it_is_back(devices):
    now = 1_800_000_000
    devices.append(dev("nadi-recv-1", "csi", now - 10, ["room1"]))
    assert monitor.check(store, now, 20, {"on": False}) == []  # reporting: nothing to say
    devices[0]["last_seen"] = now - 61  # 3 x 20 s silent
    assert monitor.check(store, now, 20, {"on": False}) == [("nadi-recv-1", "offline")]
    for t in range(1, 20):  # no repeats while it stays silent
        assert monitor.check(store, now + t * 5, 20, {"on": False}) == []
    a = kept()
    assert len(a) == 1 and a[0]["kind"] == "sensor" and a[0]["severity"] == "warning"
    assert a[0]["subject"] == "NADI: Sensor stopped reporting (Lab 2)" and "nadi-recv-1" not in a[0]["message"]
    assert "has not reported for 61 seconds" in a[0]["message"]
    devices[0]["last_seen"] = now + 100
    assert monitor.check(store, now + 101, 20, {"on": False}) == [("nadi-recv-1", "online")]
    a = kept()
    assert len(a) == 2 and a[0]["subject"] == "NADI: Sensor back online (Lab 2)" and a[0]["severity"] == "info"
    assert alerts.recent("ms", limit=1)[0]["subject"] == "NADI: Sensor kembali dalam talian (Lab 2)"


def test_critical_during_a_real_emergency_warning_during_a_drill(devices):
    now = 1_800_000_000
    devices.append(dev("nadi-recv-1", "csi", now - 100, ["room1"]))
    devices.append(dev("nadi-sim", "count", now - 100, ["room1", "room2"]))
    monitor.check(store, now, 20, {"on": True, "drill": False})
    sev = {a["subject"]: a["severity"] for a in kept()}
    assert sev == {"NADI: Sensor stopped reporting (Lab 2)": "critical",
                   "NADI: Sensor stopped reporting (Lab 2 and Hall A)": "critical"}
    store.r.delete("sensor_state", "alerts")
    monitor.check(store, now, 20, {"on": True, "drill": True})
    assert {a["severity"] for a in kept()} == {"warning"}
    assert "Lab 2 dan Hall A" in alerts.recent("ms", limit=5)[0]["subject"] + alerts.recent("ms", limit=5)[1]["subject"]


def test_climate_nodes_use_their_own_minute_interval(devices):
    now = 1_800_000_000
    devices.append(dev("nadi-climate-1", "climate", now - 100, ["room1"]))  # 100 s < 3 x 60 s: still fine
    assert monitor.check(store, now, 20, {}) == []
    devices[0]["last_seen"] = now - 181
    assert monitor.check(store, now, 20, {}) == [("nadi-climate-1", "offline")]
    assert "temperature sensor" in kept()[0]["message"] and "Sensor suhu" in alerts.recent("ms", limit=1)[0]["message"]


def test_a_device_with_several_services_uses_the_shortest_interval(devices):
    now = 1_800_000_000
    devices.append({**dev("nadi-sim", "climate", now - 70, ["room1"]), "services": ["climate", "csi"]})
    assert monitor.check(store, now, 20, {}) == [("nadi-sim", "offline")]  # 70 s > 3 x 20 s, though climate is last
    assert "occupancy sensor" in kept()[0]["message"]


def test_device_services_are_kept_in_redis():
    assert "FakeRedis" in type(store.r).__name__  # never the real Valkey
    store.save_device("nadi-sim", "csi", "room1", 10, {})
    store.save_device("nadi-sim", "climate", "room1", 10, {})
    assert store.devices()[0]["services"] == ["climate", "csi"]
    store.forget_devices(["nadi-sim"])
    assert not store.r.exists("device_services:nadi-sim")


def test_no_alert_for_retired_devices_or_after_a_restart(devices):
    now = 1_800_000_000
    devices.append(dev("old-board", "csi", now - 2 * 86400, ["room1"]))
    assert monitor.check(store, now, 20, {}) == []
    devices.append(dev("nadi-recv-2", "csi", now - 300, ["room2"]))
    assert monitor.check(store, now, 20, {}) == [("nadi-recv-2", "offline")]
    assert monitor.check(store, now + 5, 20, {}) == []  # state is in Redis: a restarted server does not repeat it


def test_background_tick_never_raises(monkeypatch, capsys):
    monkeypatch.setattr(monitor, "check", lambda *a: 1 / 0)
    main.background_tick(1)
    assert "background check failed" in capsys.readouterr().out


# --- NTP ---

def fake_ntp(offset_s):
    """A one-shot NTP server on 127.0.0.1 whose clock is offset_s ahead. Returns its port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))

    def serve():
        data, addr = sock.recvfrom(48)
        t = time.time() + offset_s + clock.NTP_EPOCH
        sec, frac = int(t), int((t % 1) * 2 ** 32)
        reply = bytearray(48)
        reply[0] = 0x24  # version 4, mode 4 (server)
        reply[32:40] = struct.pack("!II", sec, frac)
        reply[40:48] = struct.pack("!II", sec, frac)
        sock.sendto(bytes(reply), addr)
        sock.close()

    threading.Thread(target=serve, daemon=True).start()
    return sock.getsockname()[1]


def test_clock_off_by_more_than_a_minute_warns():
    assert clock.check("127.0.0.1", fake_ntp(125)) == pytest.approx(125, abs=2)
    w = clock.warning()
    assert w and w["offset_s"] == pytest.approx(125, abs=2)


def test_clock_close_enough_says_nothing():
    clock.check("127.0.0.1", fake_ntp(3))
    assert clock.warning() is None


def test_offline_skips_the_check(monkeypatch):
    clock._state.update(offset_s=500, checked=1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))  # nobody answers
    port = sock.getsockname()[1]
    monkeypatch.setattr(clock, "ntp_offset", lambda server=None, port=123, timeout=2.0: (_ for _ in ()).throw(OSError("offline")))
    assert clock.check("127.0.0.1", port) is None and clock.warning() is None
    sock.close()


def test_rooms_api_carries_the_clock_warning(monkeypatch):
    monkeypatch.setenv("NADI_MODE", "local")
    api = TestClient(main.app, client=("127.0.0.1", 5000), base_url=LOCAL_URL)
    assert api.get("/api/rooms").json()["clock"] is None
    clock._state.update(offset_s=-90.0, checked=1)
    assert api.get("/api/rooms").json()["clock"]["offset_s"] == -90.0


# --- Malaysia time ---

def test_days_and_times_are_malaysian_whatever_the_server_zone():
    ts = 1_793_660_400  # 2026-11-02 23:00:00 UTC = 2026-11-03 07:00:00 in Kuala Lumpur
    assert timeutil.day(ts) == "2026-11-03" and timeutil.clock(ts) == "07:00:00"
    assert timeutil.utc_iso(ts) == "2026-11-02T23:00:00Z"
    assert store._waste_key(ts) == "waste_rm:2026-11-03"
    assert timeutil.duration(65) == "1:05" and timeutil.duration(3723) == "1:02:03"


def test_audit_alert_time_is_malaysian(monkeypatch):
    monkeypatch.setattr(main.time, "time", lambda: 1_793_660_400)
    monkeypatch.setattr(store, "_write", lambda *a: None)
    main.set_emergency(True, "warden", "127.0.0.1")
    audit = [a for a in alerts.recent(limit=10) if "started by" in a["subject"]][0]
    assert audit["message"] == "warden at 07:00:00."


def test_long_room_lists_and_long_silences_stay_readable(devices):
    now = 1_800_000_000
    devices.append(dev("sim-local", "count", now - 3 * 3600, [f"r{i:02d}" for i in range(33)]))
    monitor.check(store, now, 20, {})
    a = kept()[0]
    assert a["subject"] == "NADI: Sensor stopped reporting (r00, r01, r02, r03, r04 and 28 more)"
    assert "for 180 minutes" in a["message"]
    assert "r04 dan 28 lagi" in alerts.recent("ms", limit=1)[0]["subject"]
