"""Send an IoTDA-style command to a board through the local Mosquitto, as the server, and print the board's reply.
Local mode only (logs in as nadi-server with MQTT_SERVER_PASSWORD from .env); never talks to Huawei Cloud.

    python scripts/send_command.py                       ac_off to nadi-climate-1
    python scripts/send_command.py --device nadi-climate-2
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="ac_off")
    ap.add_argument("--device", default="nadi-climate-1")
    ap.add_argument("--wait", type=float, default=10, help="seconds to wait for the reply")
    args = ap.parse_args()
    if os.getenv("NADI_MODE", "local").strip().lower() not in ("", "local"):
        sys.exit("send_command.py is for local mode only (NADI_MODE=local).")

    request_id = uuid.uuid4().hex[:12]
    base = f"$oc/devices/{args.device}/sys/commands"
    replies = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"nadi-command-{os.getpid()}")
    client.username_pw_set("nadi-server", os.getenv("MQTT_SERVER_PASSWORD", ""))
    client.on_message = lambda c, u, m: replies.append(m.payload.decode(errors="replace"))
    client.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")))
    client.loop_start()
    client.subscribe(f"{base}/response/request_id={request_id}", qos=1)
    time.sleep(0.5)
    body = json.dumps({"service_id": "climate", "command_name": args.command, "paras": {}})
    client.publish(f"{base}/request_id={request_id}", body, qos=1).wait_for_publish(5)
    print(f"Sent {args.command} to {args.device}. Waiting for the reply.")
    deadline = time.time() + args.wait
    while not replies and time.time() < deadline:
        time.sleep(0.1)
    client.loop_stop()
    client.disconnect()
    if not replies:
        sys.exit(f"No reply in {args.wait:.0f} s. Is the board on and connected (type status in its Serial Monitor)?")
    print(f"Reply: {replies[0]}")


if __name__ == "__main__":
    main()
