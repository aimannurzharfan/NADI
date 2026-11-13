"""DEMO_SCENARIO=on (local mode only): a fixed 3-minute story played through the normal data path.

Reports go to Mosquitto as the simulator device, exactly like a board, so ingest, checks, Redis, MySQL, alerts and the
dashboard all run for real. The story, then a 20 s pause, then it plays again:

  0:00  rooms fill up: Lab 2 to 3+, Hall A to 3+, the third room to 1
  0:30  Lab 2 empties with the air conditioning still on; the waste flag shows a minute later (10 minutes normally)
  1:30  the third room to 2: "at least 5 people, in 2 rooms"
  2:00  alarm: emergency mode with the rescue priority list; people leave room by room
  2:45  all clear: everyone out, emergency mode ends

Every room uses CSI (0, 1, 2 or 3+), which is what one sensor pair can tell. DEMO_BIG_HALL=on instead makes Hall A a
large hall with an exact counter (the "count" service, 0 to 1000) that passes 100 people: a phase 2 idea, shown on
every screen as a simulated counter. It changes by at most 15 people per step so it passes the plausibility check.

Lab 2 is the room named "Lab 2" in ROOM_NAMES (else room1). Each run starts with no alarm and an empty alerts list.
Do not run sim/fake_sensor.py at the same time.
"""
import json
import os
import random
import threading
import time

from server import config, energy, model, store
from server import plan

LENGTH_S = 180
PAUSE_S = 20
STEP_S = 5
WASTE_AFTER_S = 60
ALARM_AT, ALL_CLEAR_AT = 120, 165

# (from second, lab, hall, third room): CSI counts, 3 means 3 or more
STORY = [(0, 1, 0, 0), (10, 2, 1, 1), (20, 3, 2, 1), (25, 1, 3, 1), (30, 0, 3, 1), (90, 0, 3, 2), (130, 0, 2, 2),
         (140, 0, 1, 1), (150, 0, 0, 1), (158, 0, 0, 0), (ALL_CLEAR_AT, 0, 0, 0)]
# DEMO_BIG_HALL=on: Hall A as an exact counter, (second, people), straight lines in between
HALL = [(0, 0), (30, 45), (90, 120), (ALARM_AT, 120), (ALL_CLEAR_AT, 0)]
HALL_MAX_STEP = 15
TEMPS = (22.0, 24.0, 27.5)  # lab and hall cooled, third room with the air conditioning off

_state = {"on": False, "started": None}
_restart = threading.Event()


def big_hall():
    return os.getenv("DEMO_BIG_HALL", "").strip().lower() in ("on", "1", "true", "yes")


def enabled():
    return os.getenv("DEMO_SCENARIO", "").strip().lower() in ("on", "1", "true", "yes") and not config.is_huawei()


def status():
    """{"on": bool, "t": seconds into the story or None during the pause}."""
    if not _state["on"]:
        return {"on": False, "t": None}
    t = None if _state["started"] is None else int(time.time() - _state["started"])
    return {"on": True, "t": t if t is not None and t <= LENGTH_S else None, "length": LENGTH_S}


def restart():
    _restart.set()


def rooms():
    """(lab, hall, third) room IDs: Lab 2 by name, then the other plan rooms in order."""
    names = config.room_names()
    ids = sorted(set(plan.default_floor_rooms()) | set(names))  # the story plays on the default floor
    lab = next((r for r in ids if names.get(r, "").lower() == "lab 2"), "room1" if "room1" in ids else ids[0])
    others = [r for r in ids if r != lab]
    return lab, others[0], others[1]


def hall_at(t):
    for (t0, n0), (t1, n1) in zip(HALL, HALL[1:]):
        if t0 <= t <= t1:
            return round(n0 + (n1 - n0) * (t - t0) / (t1 - t0)) if t1 > t0 else n1
    return HALL[-1][1]


def counts_at(t):
    """(lab, hall, third room) at second t. The hall is the exact counter's count with DEMO_BIG_HALL=on."""
    lab, hall, third = [s for s in STORY if s[0] <= t][-1][1:]
    return lab, hall_at(t) if big_hall() else hall, third


_features = {}


def features_for(count):
    """CSI features the active headcount rule (model or thresholds) turns into this count, from the simulator's
    room model. Cached per count."""
    if count not in _features:
        from sim.fake_sensor import Room
        room, pick = Room("demo"), None
        room.people = count
        for _ in range(400):
            p = room.csi(0)
            if model.headcount(p)[0] == count:
                pick = p
                break
        if pick is None:
            print(f"demo: no simulated reading gives {count} people with the current rule; using one anyway", flush=True)
            pick = room.csi(0)
        _features[count] = {k: pick[k] for k in ("motion_mean", "motion_std", "amp_var", "rssi_mean", "n_packets")}
    return _features[count]


def report(t, ts):
    services = []
    for i, (room_id, count, temp) in enumerate(zip(rooms(), counts_at(t), TEMPS)):
        if i == 1 and big_hall():  # Hall A: an exact counter (phase 2)
            services.append({"service_id": "count", "properties": {"room_id": room_id, "ts": ts, "headcount": count}})
        else:
            services.append({"service_id": "csi", "properties": {"room_id": room_id, "ts": ts, **features_for(count)}})
        services.append({"service_id": "climate", "properties": {
            "room_id": room_id, "ts": ts, "temp_c": round(temp + random.uniform(-0.2, 0.2), 1),
            "humidity": round(random.uniform(58, 64), 1)}})
    return {"services": services}


def reset_rooms():
    """Start each run clean: no waste timer (so the waste alert shows again) and no alerts from earlier runs.
    A waste stretch still running is counted in today's total first, as if the room had filled up again."""
    store.r.delete("alerts")
    now = int(time.time())
    for room_id in rooms():
        room = store.room(room_id)
        if room is not None:
            energy.add_ended(energy.ended(room["empty_cold_since"], None, now, room_id), now, room_id)
        store.r.hdel(f"room:{room_id}", "empty_cold_since", "waste_alert_ts")


def start(set_emergency):
    """Run the story in a background thread. set_emergency(on, who, ip) is the same function the API uses."""
    import paho.mqtt.client as mqtt

    from scripts.mqtt_users import device_password_key

    device = os.getenv("SIM_DEVICE_ID", "nadi-sim")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{device}-demo-{os.getpid()}")
    client.username_pw_set(device, os.getenv(device_password_key(device), ""))
    client.reconnect_delay_set(1, 10)
    client.connect_async(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), keepalive=60)
    client.loop_start()
    topic = f"$oc/devices/{device}/sys/properties/report"
    energy.delay_override_s = WASTE_AFTER_S  # the story flags waste after a minute, whatever the saved delay is
    _state["on"] = True

    def play():
        while True:
            _restart.clear()
            try:
                set_emergency(False, "demo", "demo")
                reset_rooms()
            except Exception as e:
                print(f"demo: reset failed: {e}", flush=True)
            _state["started"] = time.time()
            print("demo scenario: story started", flush=True)
            alarm = clear = False
            while not _restart.is_set():
                t = time.time() - _state["started"]
                if t > LENGTH_S:
                    break
                if t >= ALARM_AT and not alarm:
                    alarm = True
                    set_emergency(True, "demo", "demo")
                if t >= ALL_CLEAR_AT and not clear:
                    clear = True
                    set_emergency(False, "demo", "demo")
                client.publish(topic, json.dumps(report(t, int(time.time()))), qos=1)
                _restart.wait(STEP_S)
            if _restart.is_set():
                continue
            _state["started"] = None
            _restart.wait(PAUSE_S)

    def safe_play():
        try:
            play()
        except Exception as e:  # never take the server down
            print(f"demo scenario stopped: {e}", flush=True)
            _state["on"] = False

    threading.Thread(target=safe_play, daemon=True, name="nadi-demo").start()
    return client
