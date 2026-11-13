"""Fake ESP32 boards: publish exactly what the firmware publishes, to the local Mosquitto, before real boards exist.

The JSON is built from the firmware's own format strings, read from the source at run time:
  NADI_CSI_JSON_FMT, NADI_REPORT_TOPIC_FMT   firmware/csi_recv/main/report.h
  CLIMATE_JSON_FMT                           firmware/climate_node/climate_node.ino
so if the firmware's JSON changes, this script sends the new bytes too.

Logs in like a board: username = device ID, password = that device's MQTT_PASSWORD_<ID>, to MQTT_LAN_IP (the address
the boards use) or 127.0.0.1 if that is empty. Local mode only; never talks to Huawei Cloud.

    python sim/fake_board.py --check      one report each, then confirm the server stored the same values
    python sim/fake_board.py              keep sending, alternating a still room and someone walking
"""
import argparse
import ast
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.mqtt_users import device_password_key  # noqa: E402

REPORT_H = ROOT / "firmware" / "csi_recv" / "main" / "report.h"
CLIMATE_INO = ROOT / "firmware" / "climate_node" / "climate_node.ino"
MAX_MSG_BYTES = 4096  # IoTDA per-message limit

# Feature values for a still room and for someone walking, taken from the firmware host test
# (firmware/csi_recv/test): real boards will give different numbers until calibrated.
STILL = {"motion_mean": 0.0170, "motion_std": 0.0018, "amp_var": 0.000412, "rssi_mean": -51.0, "n_packets": 1000}
WALKING = {"motion_mean": 0.1977, "motion_std": 0.0342, "amp_var": 0.046265, "rssi_mean": -51.0, "n_packets": 1000}
# Board health sent with every report (firmware 1.1): same field order as the C format strings
HEALTH = {"fw_version": "1.1.0", "uptime_s": 3600, "wifi_rssi": -55, "free_heap": 180000, "dropped": 0}
HEALTH_ORDER = ("fw_version", "uptime_s", "wifi_rssi", "free_heap", "dropped")


def c_define(path, name):
    """The string value of `#define NAME "..."` in a C file, as Python text."""
    m = re.search(rf'^#define {name} ("(?:[^"\\]|\\.)*")\s*$', path.read_text(encoding="utf-8"), flags=re.M)
    if not m:
        raise SystemExit(f"{name} not found in {path.relative_to(ROOT)}")
    return ast.literal_eval(m.group(1))  # C and Python agree on \" escapes


def python_format(c_fmt):
    """C printf format to Python % format. %s, %d and %.Nf behave the same in both."""
    return c_fmt.replace("%lld", "%d").replace("%lu", "%d")


def csi_payload(room_id, ts, f, health=None):
    h = health or HEALTH
    fmt = python_format(c_define(REPORT_H, "NADI_CSI_JSON_FMT"))
    return fmt % (room_id, ts, f["motion_mean"], f["motion_std"], f["amp_var"], f["rssi_mean"], f["n_packets"],
                  *(h[k] for k in HEALTH_ORDER))


def climate_payload(room_id, ts, temp_c, humidity, health=None):
    h = health or HEALTH
    return python_format(c_define(CLIMATE_INO, "CLIMATE_JSON_FMT")) % (room_id, ts, temp_c, humidity,
                                                                       *(h[k] for k in HEALTH_ORDER))


def report_topic(device_id):
    return c_define(REPORT_H, "NADI_REPORT_TOPIC_FMT") % device_id


def connect(device_id):
    import paho.mqtt.client as mqtt

    host = os.getenv("MQTT_LAN_IP") or "127.0.0.1"
    port = int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=device_id)
    client.username_pw_set(device_id, os.getenv(device_password_key(device_id), ""))
    result = {}
    client.on_connect = lambda c, u, f, rc, p: result.setdefault("rc", rc)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    for _ in range(50):
        if "rc" in result:
            break
        time.sleep(0.1)
    rc = result.get("rc")
    print(f"{device_id} -> MQTT {host}:{port}: {rc}")
    if rc is None or rc.is_failure:
        raise SystemExit("Login failed. Run python scripts/mqtt_users.py, check the device ID is in MQTT_DEVICE_IDS, "
                         "and that Mosquitto is running (docker compose up -d mosquitto).")
    return client


def publish(client, topic, payload):
    data = payload.encode()
    assert len(data) <= MAX_MSG_BYTES, f"{len(data)} bytes is over the 4 KB IoTDA limit"
    client.publish(topic, data, qos=1).wait_for_publish(5)
    print(f"{topic}  {payload}")


def check(room_id, ts, sent_csi, sent_climate, server, device_ids=()):
    """Wait for the server to store both reports, then compare stored values with what was sent."""
    from server import store

    deadline = time.time() + 10
    csi_row = climate_row = None
    while time.time() < deadline and not (csi_row and climate_row):
        time.sleep(0.5)
        with store.mysql() as conn, conn.cursor() as cur:
            cur.execute("SELECT motion_mean, motion_std, amp_var, rssi_mean, n_packets FROM occupancy "
                        "WHERE room_id=%s AND ts=%s", (room_id, ts))
            csi_row = cur.fetchone()
            cur.execute("SELECT temp_c, humidity FROM climate WHERE room_id=%s AND ts=%s", (room_id, ts))
            climate_row = cur.fetchone()
    ok = True
    sent = json.loads(sent_csi)["services"][0]["properties"]
    if not csi_row:
        print("FAIL  the server did not store the CSI report (is it running with NADI_MODE=local?)")
        ok = False
    else:
        stored = dict(zip(("motion_mean", "motion_std", "amp_var", "rssi_mean", "n_packets"), csi_row))
        same = all(abs(float(stored[k]) - float(sent[k])) <= 1e-6 * max(1.0, abs(float(sent[k]))) for k in stored)
        print(f"{'PASS' if same else 'FAIL'}  CSI report stored: {stored}")
        ok &= same
    sent_c = json.loads(sent_climate)["services"][0]["properties"]
    if not climate_row:
        print("FAIL  the server did not store the climate report")
        ok = False
    else:
        same = abs(climate_row[0] - sent_c["temp_c"]) < 1e-4 and abs(climate_row[1] - sent_c["humidity"]) < 1e-4
        print(f"{'PASS' if same else 'FAIL'}  climate report stored: temp_c {climate_row[0]:.1f}, humidity {climate_row[1]:.1f}")
        ok &= same
    with urllib.request.urlopen(f"{server}/api/rooms", timeout=5) as resp:
        room = next((r for r in json.load(resp)["rooms"] if r["room_id"] == room_id), None)
    live = bool(room and room["count_ts"] == ts and room["live"])
    print(f"{'PASS' if live else 'FAIL'}  dashboard API shows {room_id} live from this report "
          f"(headcount {room and room['headcount']})")
    req = urllib.request.Request(f"{server}/api/devices", headers={"X-Admin-Token": os.getenv("ADMIN_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=5) as resp:  # admin only: localhost, or the token from .env
        devices = {d["device_id"]: d for d in json.load(resp)["devices"]}
    healthy = True
    for device_id in device_ids:
        d = devices.get(device_id)
        good = bool(d and d["online"] and d["fw_version"] == HEALTH["fw_version"] and d["wifi_rssi"] == HEALTH["wifi_rssi"])
        print(f"{'PASS' if good else 'FAIL'}  sensor list shows {device_id} online with its health "
              f"(firmware {d and d['fw_version']}, Wi-Fi {d and d['wifi_rssi']} dBm, uptime {d and d['uptime_s']} s)")
        healthy &= good
    return ok and live and healthy


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="send once and confirm the server stored it")
    ap.add_argument("--room", default="room1")
    ap.add_argument("--recv-id", default="nadi-recv-1", help="device ID of the CSI receiver")
    ap.add_argument("--climate-id", default="nadi-climate-1", help="device ID of the climate node")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    if os.getenv("NADI_MODE", "local").strip().lower() not in ("", "local"):
        raise SystemExit("fake_board.py is for local mode only (NADI_MODE=local).")

    recv, climate = connect(args.recv_id), connect(args.climate_id)
    interval = max(10, int(os.getenv("REPORT_INTERVAL_S", "20")))
    walking = False
    started = time.time()
    try:
        while True:
            ts = int(time.time())
            health = {**HEALTH, "uptime_s": int(time.time() - started)}
            csi = csi_payload(args.room, ts, WALKING if walking else STILL, health)
            clim = climate_payload(args.room, ts, 24.3, 61.5, health)
            publish(recv, report_topic(args.recv_id), csi)
            publish(climate, report_topic(args.climate_id), clim)
            if args.check:
                sys.exit(0 if check(args.room, ts, csi, clim, args.server, (args.recv_id, args.climate_id)) else 1)
            walking = not walking
            time.sleep(interval)
    finally:
        for c in (recv, climate):
            c.loop_stop()
            c.disconnect()


if __name__ == "__main__":
    main()
