"""Fake NADI sensor: sends one combined csi + climate report for all rooms every REPORT_INTERVAL_S (default 20 s).

IoTDA free tier is 10,000 messages/day across all devices, so never go below 10 s.

Where it sends depends on NADI_MODE in .env (same topic and JSON as the real receiver either way):
  local  (default): local Mosquitto at MQTT_HOST:MQTT_PORT, no Huawei Cloud calls
  huawei:           Huawei IoTDA over MQTT (TLS) with the device ID/secret from .env
--local URL: skip MQTT and POST the IoTDA forwarding envelope straight to the server.

    python sim/fake_sensor.py
    python sim/fake_sensor.py --local http://127.0.0.1:8000/iotda
"""
import argparse
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.mqtt_users import device_password_key  # noqa: E402

load_dotenv()

for _stream in (sys.stdout, sys.stderr):  # UTF-8 on Windows consoles and redirected logs
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MIN_INTERVAL_S = 10   # IoTDA SUF budget, see project brief "Huawei Cloud limits"
INTERVAL_S = max(MIN_INTERVAL_S, int(os.getenv("REPORT_INTERVAL_S", "20")))
MAX_MSG_BYTES = 4096  # IoTDA per-message limit
ROOMS = [r.strip() for r in os.getenv("SIM_ROOMS", "room1,room2").split(",") if r.strip()]


class Room:
    """One room with a true headcount that drifts, and an aircon that may be left on."""

    def __init__(self, room_id):
        self.room_id = room_id
        self.people = random.randint(0, 3)
        self.ac_on = random.random() < 0.7
        self.temp = 24.0 if self.ac_on else 29.0

    def step(self):
        if random.random() < 0.15:
            self.people = max(0, min(5, self.people + random.choice([-1, 1])))
        if random.random() < 0.02:
            self.ac_on = not self.ac_on
        target = 23.5 if self.ac_on else 29.5
        self.temp += (target - self.temp) * 0.1 + random.gauss(0, 0.05)

    def csi(self, ts):
        h = self.people
        return {
            "room_id": self.room_id,
            "ts": ts,
            "motion_mean": round(max(0.0, 0.03 + 0.4 * h + random.gauss(0, 0.08)), 3),
            "motion_std": round(max(0.0, 0.05 + 0.6 * h + random.gauss(0, 0.1)), 3),
            "amp_var": round(max(0.0, 1.0 + 2.5 * h + random.gauss(0, 0.5)), 3),
            "rssi_mean": round(-50.0 + random.gauss(0, 1.5), 1),
            "n_packets": random.randint(480, 500),
        }

    def climate(self, ts):
        return {
            "room_id": self.room_id,
            "ts": ts,
            "temp_c": round(self.temp, 1),
            "humidity": round(random.uniform(55, 70), 1),
        }


def report(rooms, ts):
    services = []
    for room in rooms:
        services.append({"service_id": "csi", "properties": room.csi(ts)})
        services.append({"service_id": "climate", "properties": room.climate(ts)})
    return {"services": services}


def mode():
    m = os.getenv("NADI_MODE", "local").strip().lower() or "local"
    if m not in ("local", "huawei"):
        raise SystemExit(f"NADI_MODE must be local or huawei, got {m!r}")
    return m


def report_topic(device_id):
    return f"$oc/devices/{device_id}/sys/properties/report"


def local_mqtt_client():
    """Local Mosquitto (docker compose), plain MQTT, logs in as SIM_DEVICE_ID with its own password."""
    import paho.mqtt.client as mqtt

    device_id = os.getenv("SIM_DEVICE_ID", "nadi-sim")
    host, port = os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device_id}-{os.getpid()}")
    client.username_pw_set(device_id, os.getenv(device_password_key(device_id), ""))
    client.on_connect = lambda c, u, f, rc, p: print(f"local MQTT {host}:{port} connect: {rc}")
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client, report_topic(device_id)


def mqtt_client():
    import paho.mqtt.client as mqtt

    device_id = os.environ["IOTDA_DEVICE_ID"]
    secret = os.environ["IOTDA_DEVICE_SECRET"]
    # IoTDA auth: client id {device_id}_0_0_{YYYYMMDDHH}, password = HMAC-SHA256(key=timestamp, msg=secret)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    password = hmac.new(stamp.encode(), secret.encode(), hashlib.sha256).hexdigest()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device_id}_0_0_{stamp}")
    client.username_pw_set(device_id, password)
    client.tls_set(ca_certs=os.getenv("IOTDA_CA_CERT") or None)
    client.on_connect = lambda c, u, f, rc, p: print(f"MQTT connect: {rc}")
    client.on_disconnect = lambda c, u, f, rc, p: print(f"MQTT disconnect: {rc}")
    client.connect(os.environ["IOTDA_HOST"], int(os.getenv("IOTDA_PORT", "8883")), keepalive=60)
    client.loop_start()
    return client, report_topic(device_id)


def post_local(url, payload):
    # Same shape IoTDA uses for HTTP data forwarding of property reports
    envelope = {
        "resource": "device.property",
        "event": "report",
        "event_time": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "notify_data": {"header": {"device_id": "sim-local"}, "body": payload},
    }
    token = os.getenv("INGEST_TOKEN")
    if token:
        url += ("&" if "?" in url else "?") + "token=" + token
    req = urllib.request.Request(
        url, data=json.dumps(envelope).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", metavar="URL", help="POST to the server directly instead of MQTT")
    args = ap.parse_args()

    target = "HTTP " + args.local if args.local else "Huawei IoTDA" if mode() == "huawei" else "local Mosquitto"
    print(f"sending one report for {len(ROOMS)} rooms every {INTERVAL_S} s to {target}", flush=True)
    rooms = [Room(r) for r in ROOMS]
    client = topic = None
    if not args.local:
        client, topic = mqtt_client() if mode() == "huawei" else local_mqtt_client()

    while True:
        for room in rooms:
            room.step()
        payload = report(rooms, int(time.time()))
        size = len(json.dumps(payload))
        if size > MAX_MSG_BYTES:
            print(f"report is {size} bytes, over the IoTDA 4 KB limit: use fewer rooms", flush=True)
        try:
            if args.local:
                status = post_local(args.local, payload)
            else:
                status = client.publish(topic, json.dumps(payload), qos=1).rc
            print(status, " ".join(f"{r.room_id}={r.people}p/{r.temp:.1f}C" for r in rooms), flush=True)
        except Exception as e:
            print("send failed:", e, flush=True)
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
