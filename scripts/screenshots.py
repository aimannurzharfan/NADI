"""Save the README and user-guide screenshots of the web console to docs/screenshots/ (1920x1080, phone for /label).

    overview.png        everyday overview
    floor-drawer.png    floor plan with a room's details open
    rooms.png           rooms table
    sensors.png         sensor list and board address (admin)
    energy.png          air conditioning waste
    alerts.png          alerts with severity and acknowledgement
    emergency.png       emergency takeover (started and ended again by this script)
    chat.png            one English and one Bahasa Melayu answer
    label-phone.png     /label at phone width
    offline-banner.png  the "service offline" banner (shown by replaying the API answer with MySQL offline)
    demo.png            only with --demo, against a server started with DEMO_SCENARIO=on

Needs the server and simulator running, on the server computer (admin pages) or with ADMIN_TOKEN exported here.
Uses Microsoft Edge if installed, otherwise Playwright's Chromium (python -m playwright install chromium).

    python scripts/screenshots.py [--url http://127.0.0.1:8000] [--only chat,emergency] [--demo]
"""
import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SHOTS = ("overview", "floor-drawer", "rooms", "sensors", "energy", "alerts", "emergency", "chat", "label-phone", "offline-banner")


def emergency(url, on):
    req = urllib.request.Request(f"{url}/api/emergency", data=json.dumps({"on": on}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Admin-Token": os.getenv("ADMIN_TOKEN", "")})
    urllib.request.urlopen(req, timeout=10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--only", default="")
    ap.add_argument("--demo", action="store_true", help="also demo.png (server running with DEMO_SCENARIO=on)")
    args = ap.parse_args()
    want = set(args.only.split(",")) if args.only else set(SHOTS) | ({"demo"} if args.demo else set())
    OUT.mkdir(parents=True, exist_ok=True)
    token = os.getenv("ADMIN_TOKEN", "")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, reduced_motion="reduce")
        if token:
            ctx.add_init_script(f"sessionStorage.setItem('nadiAdminToken', {json.dumps(token)})")
        page = ctx.new_page()

        def shot(name, path, before=None, wait=2500):
            if name not in want:
                return
            page.goto(args.url + path)
            page.wait_for_timeout(wait)
            if before:
                before()
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("saved", name)

        shot("overview", "/")
        shot("floor-drawer", "/floor?room=room2", wait=3500)
        shot("rooms", "/rooms")
        shot("sensors", "/sensors")
        shot("energy", "/energy")
        shot("alerts", "/alerts")
        if "emergency" in want:
            emergency(args.url, True)
            try:
                shot("emergency", "/", wait=3000)
            finally:
                emergency(args.url, False)

        def ask():
            page.get_by_role("button", name="Ask NADI").click()
            for q in ("Which room should rescuers check first?", "Berapa orang di dalam?"):
                page.get_by_label("Question").fill(q)
                page.get_by_label("Question").press("Enter")
                page.wait_for_timeout(3000)
        shot("chat", "/", before=ask)

        if "offline-banner" in want:
            def offline(route):
                r = route.fetch()
                data = r.json()
                data["offline"] = {"mysql": int(time.time()) - 600}
                route.fulfill(response=r, body=json.dumps(data))
            page.route("**/api/rooms?*", offline)
            shot("offline-banner", "/")
            page.unroute("**/api/rooms?*")
        if "demo" in want:
            def wait_demo():
                page.wait_for_function("document.body.innerText.includes('DEMO SCENARIO')", timeout=20000)
            shot("demo", "/", before=wait_demo)

        if "label-phone" in want:
            phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
            if token:
                phone.add_init_script(f"sessionStorage.setItem('nadiAdminToken', {json.dumps(token)})")
            pp = phone.new_page()
            pp.goto(args.url + "/label")
            pp.wait_for_timeout(2500)
            pp.screenshot(path=str(OUT / "label-phone.png"), full_page=True)
            print("saved label-phone")
        browser.close()


if __name__ == "__main__":
    main()
