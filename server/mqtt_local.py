"""NADI_MODE=local: subscribe to the local Mosquitto broker on the same topic and JSON the devices send to IoTDA.

    $oc/devices/{device_id}/sys/properties/report   {"services": [...]}

paho reconnects on its own, so the server can start before the broker.
MQTT_TLS=on connects over TLS (port 8883 by default) with the CA made by scripts/mqtt_tls.py.
"""
import json
import os

import paho.mqtt.client as mqtt

from server import health

TOPIC = "$oc/devices/+/sys/properties/report"
MAX_MSG_BYTES = 4096  # same limit as IoTDA, so nothing works locally that would fail in the cloud


def services_from_payload(payload):
    """Decode an MQTT payload into a services list. A non-object body (e.g. a bare array or
    number) yields an empty list instead of crashing; bad JSON raises so the caller can log it."""
    data = json.loads(payload)
    if not isinstance(data, dict):
        return []
    return data.get("services") or []


def start(on_services):
    """on_services(services, device_id) is called for every report from an allowed device."""
    host = os.getenv("MQTT_HOST", "127.0.0.1")
    tls = os.getenv("MQTT_TLS", "").strip().lower() in ("on", "1", "true", "yes")
    port = int(os.getenv("MQTT_PORT", "8883" if tls else "1883"))
    # The broker only lets in nadi-server and the device IDs in MQTT_DEVICE_IDS (scripts/mqtt_users.py).
    # The same list is checked here too, so a device left in the passwd file but removed from .env is ignored.
    allowed = {d.strip() for d in os.getenv("MQTT_DEVICE_IDS", "").split(",") if d.strip()}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"nadi-server-{os.getpid()}")
    client.username_pw_set("nadi-server", os.getenv("MQTT_SERVER_PASSWORD", ""))
    if tls:  # MQTT_TLS=on: the broker's own CA from scripts/mqtt_tls.py; certificate and host name are checked
        client.tls_set(ca_certs=os.getenv("MQTT_CA_FILE", "deploy/mosquitto/certs/ca.crt"))

    def on_connect(c, userdata, flags, rc, props):
        print(f"local MQTT {host}:{port} connect: {rc}", flush=True)
        health.mark("mqtt", not rc.is_failure)
        if not rc.is_failure:
            c.subscribe(TOPIC, qos=1)

    def on_disconnect(c, userdata, flags, rc, props):
        health.mark("mqtt", False)

    def on_message(c, userdata, msg):
        device_id = msg.topic.split("/")[2]
        if allowed and device_id not in allowed:
            print(f"MQTT message from unknown device {device_id!r}: dropped", flush=True)
            return
        if len(msg.payload) > MAX_MSG_BYTES:
            print(f"MQTT message on {msg.topic} is {len(msg.payload)} bytes, over 4 KB: dropped", flush=True)
            return
        try:
            on_services(services_from_payload(msg.payload), device_id)
        except Exception as e:  # a bad message must not kill the subscriber thread
            print(f"MQTT message on {msg.topic} rejected: {e}", flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_connect_fail = lambda c, userdata: health.mark("mqtt", False)  # broker not running
    client.reconnect_delay_set(min_delay=1, max_delay=10)  # back within 10 s of the broker returning (default 120)
    client.connect_async(host, port, keepalive=60)
    client.loop_start()
    return client
