"""Which dependencies are up right now, so the server can keep going and the dashboard can say what is offline.

Each dependency is marked down by the first failed call and up again by the next success. While one is down,
callers skip it for RETRY_S instead of waiting on a timeout for every request; a background thread re-checks every
RETRY_S, so recovery is picked up even when nothing else touches it.
"""
import os
import socket
import threading
import time

import pymysql
import redis

RETRY_S = 3
NAMES = ("redis", "mysql", "mqtt")
_state = {n: {"ok": True, "since": None, "tried": 0.0} for n in NAMES}
_lock = threading.Lock()


def mark(name, ok):
    with _lock:
        s = _state[name]
        if ok and not s["ok"]:
            print(f"{name} is back", flush=True)
        elif not ok and s["ok"]:
            print(f"{name} is offline", flush=True)
            s["since"] = int(time.time())
        s["ok"] = ok
        s["tried"] = time.time()
        if ok:
            s["since"] = None


def ok(name):
    return _state[name]["ok"]


def should_try(name):
    """True when name is up, or down but not tried in the last RETRY_S seconds."""
    s = _state[name]
    return s["ok"] or time.time() - s["tried"] >= RETRY_S


def down():
    """{name: unix time it went offline} for every dependency that is down now."""
    return {n: s["since"] for n, s in _state.items() if not s["ok"]}


def reset():
    for s in _state.values():
        s.update(ok=True, since=None, tried=0.0)


# --- one-off checks, also used by GET /api/health ---

def check_redis():
    """PING on a short-lived client with 2 s connect/socket timeouts."""
    client = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD") or None,
        socket_connect_timeout=2, socket_timeout=2,
    )
    try:
        return client.ping()
    finally:
        client.close()


def check_mysql():
    """SELECT 1 on a short-lived connection with a 2 s connect timeout."""
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "nadi"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "nadi"),
        connect_timeout=2, read_timeout=2, write_timeout=2,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    finally:
        conn.close()


def check_mqtt():
    """Open a TCP connection to the configured MQTT broker (2 s timeout)."""
    host = os.getenv("MQTT_HOST", "127.0.0.1")
    port = int(os.getenv("MQTT_PORT", "1883"))
    with socket.create_connection((host, port), timeout=2):
        return True


def _safe(check):
    try:
        return bool(check())
    except Exception:
        return False


def start_watch(on_mysql_back=None):
    """Background re-check of Redis and MySQL. MQTT state comes from the paho callbacks (server/mqtt_local.py)."""
    def loop():
        while True:
            time.sleep(RETRY_S)
            if not ok("redis"):
                mark("redis", _safe(check_redis))
            if not ok("mysql"):
                up = _safe(check_mysql)
                mark("mysql", up)
                if up and on_mysql_back:
                    try:
                        on_mysql_back()
                    except Exception as e:
                        print(f"writing buffered history failed: {e}", flush=True)

    threading.Thread(target=loop, daemon=True, name="nadi-health").start()
