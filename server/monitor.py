"""Sensor stopped / back online alerts.

A device that has reported before and is now silent for longer than 3 report intervals (REPORT_INTERVAL_S for CSI
receivers and counters, 60 s for climate nodes, which report once a minute) raises one "sensor offline" alert:
a warning normally, critical during a real emergency (a drill keeps it a warning). When it reports again, one
"back online" alert. The last state of each device is kept in Redis (sensor_state), so a restart does not repeat
an alert, and a device unseen for over 24 hours (retired, see the Sensors page) raises nothing more.

Alerts name rooms, never device IDs: device IDs are broker usernames and stay on the admin-only Sensors page.
"""
from server import alerts, config, logic
from server.strings import t

CLIMATE_INTERVAL_S = 60
RETIRED_S = 24 * 3600
STATE_KEY = "sensor_state"


LIST_MAX = 5  # a simulator reports for many rooms: name the first few


def room_list(names, lang):
    """"Lab 2, Hall A and Room 3", or "Lab 2, ... and 28 more" for a long list."""
    if len(names) > LIST_MAX:
        names = names[:LIST_MAX] + [t("list.more", lang, n=len(names) - LIST_MAX)]
    return logic.join_names(names, lang)


def interval(service, report_interval_s):
    return CLIMATE_INTERVAL_S if service == "climate" else report_interval_s


def check(store, now, report_interval_s, emergency):
    """One pass over every known device. Returns [(device_id, "offline" | "online")] for the changes alerted."""
    state = store.r.hgetall(STATE_KEY)
    changes = []
    names = config.room_names()
    for d in store.devices():
        if d["last_seen"] is None:
            continue
        silent = now - d["last_seen"]
        if silent > RETIRED_S:
            continue
        # a device sending several services (the simulator: csi and climate) is judged by its most frequent one
        limit = 3 * min(interval(svc, report_interval_s) for svc in d.get("services") or [d["service"]])
        now_state = "offline" if silent > limit else "online"
        before = state.get(d["device_id"])
        if before == now_state or (before is None and now_state == "online"):
            if before is None:
                store.r.hset(STATE_KEY, d["device_id"], now_state)
            continue
        store.r.hset(STATE_KEY, d["device_id"], now_state)
        listed = [config.room_name(r, names) for r in d["rooms"]] or ["–"]
        rooms, rooms_ms = room_list(listed, "en"), room_list(listed, "ms")
        kind = "sensor.kind_climate" if set(d.get("services") or [d["service"]]) == {"climate"} else "sensor.kind_count"
        if now_state == "offline":
            real = emergency.get("on") and not emergency.get("drill")
            how_long = {"seconds": int(silent)} if silent < 120 else {"minutes": int(silent // 60)}
            alerts.send("sensor", "alert.sensor_offline_subject",
                        "alert.sensor_offline_body" if silent < 120 else "alert.sensor_offline_body_minutes",
                        severity="critical" if real else "warning", rooms=rooms, rooms_ms=rooms_ms, kind_key=kind,
                        **how_long)
        else:
            alerts.send("sensor", "alert.sensor_online_subject", "alert.sensor_online_body", severity="info",
                        rooms=rooms, rooms_ms=rooms_ms, kind_key=kind)
        changes.append((d["device_id"], now_state))
    return changes
