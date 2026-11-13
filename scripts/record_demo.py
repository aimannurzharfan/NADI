"""Record the demo scenario to docs/demo/nadi_demo.webm (Playwright video, 1920x1080, about 3 minutes).

Starts Mosquitto (docker compose), its own server on port 8010 with DEMO_SCENARIO=on, plays the story from the start
and records the dashboard until the all clear. Everything it started is stopped at the end. Local mode only.

    python scripts/record_demo.py [--lang ms]
Do not run sim/fake_sensor.py or another demo server at the same time (they would mix their readings in).
"""
import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "demo"
PORT = 8010
TOKEN = "record-" + secrets.token_hex(12)


def post(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Admin-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def wait_up(url, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "/api/info", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not start: see docs/demo/record-server.log")


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=["en", "ms"], default="en")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    started_broker = subprocess.run(["docker", "compose", "ps", "--status", "running", "-q", "mosquitto"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip() == ""
    subprocess.run(["docker", "compose", "up", "-d", "mosquitto"], cwd=ROOT, capture_output=True)
    env = dict(os.environ, DEMO_SCENARIO="on", NADI_MODE="local", ADMIN_TOKEN="", ADMIN_TOKENS=f"recorder:{TOKEN}",
               PYTHONUNBUFFERED="1")
    log = open(OUT / "record-server.log", "w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--no-proxy-headers",
                               "--log-level", "warning"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{PORT}"
    video = None
    try:
        wait_up(url)
        time.sleep(3)  # demo thread connects to the broker
        post(url + "/api/demo/restart")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                      record_video_dir=str(OUT / "raw"), record_video_size={"width": 1920, "height": 1080})
            page = ctx.new_page()
            page.goto(f"{url}/?lang={args.lang}")
            print("recording 3 minutes: rooms fill, Lab 2 empties with the air conditioning on, alarm at 2:00, all clear at 2:45",
                  flush=True)
            end = time.time() + 181
            while time.time() < end:
                page.wait_for_timeout(5000)
                left = int(end - time.time())
                print(f"  {max(0, left)} s left", flush=True)
            video = page.video.path()
            ctx.close()
            browser.close()
        name = "nadi_demo.webm" if args.lang == "en" else "nadi_demo_ms.webm"
        shutil.move(video, OUT / name)
        print(f"saved {(OUT / name).relative_to(ROOT)} ({(OUT / name).stat().st_size / 2**20:.1f} MB)")
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
        shutil.rmtree(OUT / "raw", ignore_errors=True)
        if started_broker:
            subprocess.run(["docker", "compose", "stop", "mosquitto"], cwd=ROOT, capture_output=True)


if __name__ == "__main__":
    main()
