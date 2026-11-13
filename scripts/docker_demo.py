"""Start the "Try it" demo inside its container: docker compose --profile demo up --build

Not for real use (see docs/DEPLOYMENT.md). It does what the quick start does by hand:

1. .env is copied from .env.example when it is missing.
2. Broker logins: scripts/mqtt_users.py fills the empty passwords in .env and writes deploy/mosquitto/passwd.
   The broker container waits for that file.
3. The server runs on the container's own 127.0.0.1:8001 and socat passes port 8000 to it. docker-compose.yml
   publishes port 8000 on the host's 127.0.0.1 only, so the only browser that can reach it is one on the computer
   running Docker, and the server sees it as "this computer": admin without a token, the same as running the
   server directly. Nothing on the network can reach the port.

DEMO_SCENARIO=on and the service names of Valkey, MySQL and Mosquitto come from docker-compose.yml.
"""
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_PORT = 8000
SERVER_PORT = 8001


def ensure_env(root=ROOT):
    """Copy .env.example to .env when there is no .env yet. True when it made one."""
    env = root / ".env"
    if env.exists():
        return False
    shutil.copyfile(root / ".env.example", env)
    return True


def server_command(port=SERVER_PORT):
    return [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(port),
            "--no-proxy-headers", "--limit-concurrency", "200", "--timeout-keep-alive", "5"]


def relay_command(public=PUBLIC_PORT, port=SERVER_PORT):
    return ["socat", f"TCP-LISTEN:{public},fork,reuseaddr", f"TCP:127.0.0.1:{port}"]


def main():
    if ensure_env():
        print("No .env found: copied .env.example to .env.", flush=True)
    sys.path.insert(0, str(ROOT))
    from scripts import mqtt_users
    mqtt_users.main(restart_hint=False)  # the broker container starts once the file is there

    server = subprocess.Popen(server_command(), cwd=ROOT)
    relay = subprocess.Popen(relay_command(), cwd=ROOT)

    def stop(*_):
        for p in (relay, server):
            if p.poll() is None:
                p.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"NADI demo is starting. Open http://localhost:{PUBLIC_PORT} in a browser on this computer.", flush=True)
    code = server.wait()
    stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
