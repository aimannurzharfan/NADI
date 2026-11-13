"""Shared helpers for the stress scripts: start/stop a NADI server and the simulator, MQTT clients, cleanup.

Local mode only. Never talks to Huawei Cloud. Secrets are read from .env and never printed.
"""
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

for _stream in (sys.stdout, sys.stderr):  # emoji and Malay text in results on Windows consoles
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.mqtt_users import device_password_key  # noqa: E402

PY = sys.executable
RESULTS = ROOT / "scripts" / "stress" / "results"
LOGS = RESULTS / "logs"
SIM_DEVICE = os.getenv("SIM_DEVICE_ID", "nadi-sim")
TOKEN = "stress-" + secrets.token_hex(8)  # fresh admin token per run, labelled "stress" in the audit log
HEADERS = {"X-Admin-Token": TOKEN}


def server_env(**extra):
    env = dict(os.environ)
    env.update({"NADI_MODE": "local", "ADMIN_TOKEN": "", "ADMIN_TOKENS": f"stress:{TOKEN}", "VIEWER_TOKEN": "",
                "TRUSTED_PROXIES": "127.0.0.1", "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
                "INCIDENT_DIR": str(LOGS / "incidents"), "NTP_CHECK": "off"})  # reports and snapshots: not the real folder
    env.update({k: str(v) for k, v in extra.items()})
    return env


class Server:
    """uvicorn as a child process, started like production (--no-proxy-headers, --limit-concurrency 200,
    --timeout-keep-alive 5). TRUSTED_PROXIES=127.0.0.1 lets the stress clients stand in for many IPs with
    X-Forwarded-For; a request that carries it never counts as "this computer" for admin."""

    def __init__(self, port=8000, name="server", **env):
        self.port, self.name, self.env = port, name, server_env(**env)
        self.url = f"http://127.0.0.1:{port}"
        self.proc = None

    def start(self, wait_s=30):
        LOGS.mkdir(parents=True, exist_ok=True)
        self.log = open(LOGS / f"{self.name}.log", "a", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(self.port),
             "--no-proxy-headers", "--limit-concurrency", "200", "--timeout-keep-alive", "5", "--log-level", "warning"],
            cwd=ROOT, env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit(f"server exited at start-up, see {LOGS / (self.name + '.log')}")
            try:
                get(self.url + "/api/me", timeout=2)  # open even with VIEWER_TOKEN
                return self
            except Exception:
                time.sleep(0.3)
        raise SystemExit("server did not start in time")

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.alive():
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.proc is not None:
            self.log.close()

    def kill(self):
        """Hard stop, like a crash or a pulled plug."""
        if self.alive():
            self.proc.kill()
            self.proc.wait(10)
            self.log.close()


def start_sim(interval=10, name="sim"):
    LOGS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, NADI_MODE="local", REPORT_INTERVAL_S=str(interval), PYTHONUNBUFFERED="1")
    log = open(LOGS / f"{name}.log", "a", encoding="utf-8")
    return subprocess.Popen([PY, "sim/fake_sensor.py"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def request(method, url, body=None, headers=None, timeout=10):
    """(status, parsed JSON or text). Never raises on HTTP error codes."""
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode(errors="replace")


def get(url, timeout=10):
    status, body = request("GET", url, timeout=timeout)
    if status != 200:
        raise RuntimeError(f"GET {url}: {status}")
    return body


def mqtt_client(username=SIM_DEVICE, password=None, client_id=None):
    """paho client with .rc set to the broker's answer (None = no answer). password=None uses .env."""
    import paho.mqtt.client as mqtt

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or f"{username}-{secrets.token_hex(3)}")
    if username is not None:
        c.username_pw_set(username, os.getenv(device_password_key(username), "") if password is None else password)
    result = {}
    c.on_connect = lambda cl, u, f, rc, p: result.setdefault("rc", rc)
    c.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), keepalive=30)
    c.loop_start()
    for _ in range(50):
        if "rc" in result:
            break
        time.sleep(0.1)
    c.rc = result.get("rc")
    return c


def topic(device):
    return f"$oc/devices/{device}/sys/properties/report"


def docker(*args):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True).returncode == 0


def mysql_count(where, params=()):
    from server import store

    with store.mysql() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM occupancy WHERE {where}", params)
        return cur.fetchone()[0]


def cleanup_rooms(prefix):
    """Remove test rooms from Redis and MySQL so the demo dashboard is back to normal."""
    from server import store

    for room_id in [r for r in store.r.smembers("rooms") if r.startswith(prefix)]:
        store.r.srem("rooms", room_id)
        store.r.delete(f"room:{room_id}")
    for key in store.r.scan_iter(f"seen:*:{prefix}*"):
        store.r.delete(key)
    with store.mysql() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM occupancy WHERE room_id LIKE %s", (prefix + "%",))
        cur.execute("DELETE FROM climate WHERE room_id LIKE %s", (prefix + "%",))


def save(name, data):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]
