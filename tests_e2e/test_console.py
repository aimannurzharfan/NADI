"""End-to-end tests of the web console in Microsoft Edge (Playwright). They start their own NADI server and need the
Docker services (Redis, MySQL, Mosquitto) running; they are skipped otherwise.

    .\\.venv\\Scripts\\python -m pytest tests_e2e            # about 4 minutes (the demo scenario runs to the all clear)
    .\\.venv\\Scripts\\python -m pytest tests_e2e -k "not demo"  # about 40 seconds
"""
import csv
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pw = pytest.importorskip("playwright.sync_api")


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def mysql_port():
    from dotenv import dotenv_values
    return int(dotenv_values(ROOT / ".env").get("MYSQL_PORT") or 3306)


pytestmark = pytest.mark.skipif(not (port_open(6379) and port_open(mysql_port()) and port_open(1883)),
                                reason="needs Docker Redis, MySQL and Mosquitto (docker compose up -d)")


def start_server(port, tmp_path, **env):
    full = dict(os.environ, NADI_MODE="local", ADMIN_TOKEN="", ADMIN_TOKENS="", LABELS_PATH=str(tmp_path / "labels.csv"),
                INCIDENT_DIR=str(tmp_path / "incidents"), NTP_CHECK="off",
                SITE_DIR=str(tmp_path / "site"),  # plans an e2e test saves never reach data/site
                # every page of every test comes from 127.0.0.1 within a few minutes; one real console makes about 34
                # reads a minute, so the default 240 stays for real use (the limits are tested in tests/test_hardening.py)
                READ_PER_MIN="5000", HISTORY_PER_MIN="5000",
                ROOM_NAMES="",  # rooms go by the names on the floor plan, whatever the developer settings say
                INGEST_TOKEN="",  # reports posted from this computer by push() below are accepted
                PYTHONUNBUFFERED="1", **env)
    log = open(tmp_path / f"server-{port}.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers",
                             "--log-level", "warning"], cwd=ROOT, env=full, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/me", timeout=1)  # open even with VIEWER_TOKEN
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    pytest.fail("server did not start")


def push(url, room_id, motion_std):
    """One CSI report for a room, sent the way IoTDA forwards it (allowed from this computer without a token)."""
    props = {"room_id": room_id, "ts": int(time.time()), "motion_mean": motion_std / 2, "motion_std": motion_std,
             "amp_var": 0.1, "rssi_mean": -50.0, "n_packets": 500}
    body = {"resource": "device.property", "notify_data": {"body": {"services": [{"service_id": "csi", "properties": props}]}}}
    req = urllib.request.Request(url + "/iotda", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        if e.code != 429:  # the room reported a moment ago: it is live already
            raise


SMALL_TEXT = """(root) => [...document.querySelectorAll(root + ' *')].filter((e) => e.children.length === 0
    && e.textContent.trim() && e.getClientRects().length && !e.closest('svg') && !e.closest('.sr-only')
    && parseFloat(getComputedStyle(e).fontSize) < 14).map((e) => e.textContent.trim().slice(0, 30))"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("console")
    proc = start_server(8031, tmp)
    for room_id in ("room1", "room2"):  # the tests do not depend on what the database held before
        push("http://127.0.0.1:8031", room_id, 0.2)
    yield "http://127.0.0.1:8031", tmp
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    ctx.close()


def test_overview_loads(server, page):
    """The overview: building summary with the live chip, the status pills by group, live plan, attention queue,
    activity, people, today and detection. At 1366x768 the whole plan shows without scrolling, the page never
    scrolls sideways and nothing is under 14 px, in the page or in the frame around it."""
    url, _ = server
    page.goto(url + "/")
    page.get_by_role("heading", name="Building summary", level=1).wait_for()
    page.locator("[data-live-chip]").wait_for()
    overall = page.locator("[data-overall]")
    overall.wait_for()
    assert re.search("All clear|need|No live data|Not updating", overall.inner_text()), overall.inner_text()
    assert page.locator("[data-group]").count() == 3  # air conditioning waste today (the highlight), rooms, sensors
    assert re.fullmatch(r"RM \d+\.\d\d", page.locator("[data-waste-rm]").inner_text())
    page.get_by_role("group", name="Floor plan").wait_for()
    for title in ("Building status", "Live floor plan", "Needs attention", "Live activity", "People", "Today's summary",
                  "Detection"):
        page.get_by_role("heading", name=title).wait_for()
    info = page.request.get(url + "/api/info").json()["detector"]
    live = page.locator("[data-live-detector]").inner_text()
    assert ("MindSpore" in live) == (info["mode"] == "model"), live  # MindSpore is the live detector only when it is
    page.get_by_text("Peak people today").wait_for()
    page.get_by_text("Sensor uptime today").wait_for()
    assert page.get_by_role("link", name="Sensors").is_visible()
    assert page.get_by_role("button", name="Start emergency mode").first.is_visible()
    plan = page.get_by_role("group", name="Floor plan").bounding_box()
    assert plan["y"] + plan["height"] <= 768, plan  # the whole plan, without scrolling
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    small = page.evaluate(SMALL_TEXT, "body")
    assert not small, f"text under 14 px on the overview: {small}"
    assert not page.errors


def test_frame_sidebar_ask_box_and_bell(server, page):
    """The frame: the sidebar is an icon rail at 1366 px, opens with the hamburger and stays open after a reload; a
    question typed in the header box is answered in the side panel; Escape closes it and the box has the focus again."""
    url, _ = server
    page.goto(url + "/")
    side = page.locator("#sidebar")
    side.wait_for()
    assert side.get_attribute("data-sidebar") == "rail"
    assert side.bounding_box()["width"] <= 80
    for name in ("Overview", "Floor plan", "Rooms", "Sensors", "Energy", "Calibration"):
        link = side.get_by_role("link", name=name, exact=True)
        box = link.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 80, (name, box)  # inside the rail, not cut off
    menu = page.locator("[data-menu]")
    assert menu.get_attribute("aria-expanded") == "false" and menu.get_attribute("aria-controls") == "sidebar"
    menu.click()
    page.locator("#sidebar[data-sidebar=open]").wait_for()
    assert page.locator("[data-menu]").get_attribute("aria-expanded") == "true"
    side.get_by_text("Level 4").wait_for()
    page.reload()
    page.locator("#sidebar[data-sidebar=open]").wait_for()  # remembered in this browser
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("[data-bell]").get_attribute("href") == "/alerts"

    page.keyboard.press("/")
    box = page.get_by_role("textbox", name="Ask NADI a question")
    assert box.evaluate("e => e === document.activeElement")
    box.press("Enter")  # nothing typed: the panel opens with its suggested questions
    page.locator("[data-ask-panel] [data-suggestions] button").first.wait_for()
    assert page.locator("[data-ask-panel] [data-suggestions] button").count() == 3
    page.keyboard.press("Escape")
    page.get_by_role("dialog", name="Ask NADI").wait_for(state="detached")
    box.fill("How many people are inside?")
    box.press("Enter")
    panel = page.get_by_role("dialog", name="Ask NADI")
    panel.locator("[data-line=q]").get_by_text("How many people are inside?").wait_for()
    page.wait_for_function("() => document.querySelectorAll('[data-ask-panel] [data-line=a]').length === 1", timeout=20000)
    assert panel.locator("[data-line=q]").count() == 1  # sent once
    assert re.search("people|person|No one", panel.locator("[data-line=a]").inner_text())
    assert not page.evaluate(SMALL_TEXT, "[data-ask-panel]")
    page.keyboard.press("Escape")
    panel.wait_for(state="detached")
    page.wait_for_function("() => !!document.activeElement && document.activeElement.getAttribute('aria-label') === 'Ask NADI a question'")
    assert not page.errors


def test_overview_signal_endpoint_and_keyboard(server, page):
    """The signal endpoint answers for a known room and refuses an unknown one; a keyboard user can reach the page's
    links and room tiles, each with a visible focus ring."""
    url, _ = server
    ok = page.request.get(url + "/api/rooms/room1/signal?minutes=999")
    assert ok.status == 200
    body = ok.json()
    assert body["room_id"] == "room1" and body["minutes"] == 60 and isinstance(body["points"], list)
    assert page.request.get(url + "/api/rooms/nope/signal").status == 422
    every = page.request.get(url + "/api/signals?minutes=999")
    assert every.status == 200
    body = every.json()
    assert body["minutes"] == 10 and body["truncated"] is False and body["rooms"]["room1"]["room_id"] == "room1"
    page.goto(url + "/")
    page.get_by_role("group", name="Floor plan").wait_for()
    seen = set()
    for _ in range(40):
        page.keyboard.press("Tab")
        info = page.evaluate("""() => { const e = document.activeElement; const s = getComputedStyle(e);
            return { main: !!e.closest('#main'), tag: e.tagName, name: e.getAttribute('aria-label') || e.textContent.trim().slice(0, 40),
                     ring: s.outlineStyle !== 'none' || s.boxShadow !== 'none' } }""")
        if info["main"]:
            assert info["ring"], f"no visible focus on {info}"
            seen.add(info["name"])
    assert "All alerts" in seen or any(s.startswith("View all") for s in seen), seen  # the feed's link to the Alerts page
    assert not page.errors


def test_overview_is_still_during_a_drill(server, page):
    """Emergency or drill: the takeover covers the overview and nothing on it animates."""
    url, _ = server
    page.goto(url + "/")
    page.get_by_role("group", name="Floor plan").wait_for()
    assert page.locator("[data-still]").count() == 1  # the tests ask for reduced motion: already still
    page.get_by_role("button", name="Start emergency mode").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Start drill").click()
    takeover = page.get_by_role("alertdialog", name="Drill")
    takeover.wait_for()
    page.wait_for_function("document.querySelector('[role=status][data-level]')?.dataset.level === 'act'")
    assert page.locator(".live-beat, .report-pulse, .slide-in").count() == 0
    takeover.get_by_role("button", name="End drill").click()
    takeover.get_by_role("button", name="End the drill on every screen").click()
    takeover.wait_for(state="detached", timeout=10000)
    assert not page.errors


def test_open_room_drawer(server, page):
    """A room that reports: its panel opens on the count and the nearest exit, then the people chart, the Signal
    section (pair picture driven by the latest report, live chart of the last 5 minutes) and the climate chart, in
    that order, with nothing under 14 px."""
    url, _ = server
    push(url, "room2", 0.2)
    page.goto(url + "/floor")
    page.get_by_role("button", name="Hall A:").first.click()
    drawer = page.get_by_role("dialog")
    drawer.get_by_role("heading", name="Hall A").wait_for()
    drawer.get_by_role("heading", name="Signal", exact=True).wait_for()
    drawer.locator("[data-pair=calm]").wait_for()  # 0.2 dB is under any threshold in use
    drawer.get_by_role("heading", name="Live signal").wait_for()
    assert drawer.locator("[data-person]").count() == 0 and drawer.locator(".wave-travel").count() == 0
    drawer.get_by_text("Temperature and humidity").wait_for()
    assert drawer.locator("[data-room-count]").inner_text().startswith("0")
    assert drawer.locator("[data-room-exit]").inner_text() == "Nearest exit: Stair A"
    drawer.get_by_role("heading", name="People").wait_for()
    drawer.get_by_role("combobox", name="Time range").wait_for()  # the people chart's range; the signal has none
    tops = page.evaluate("""() => { const d = document.querySelector('[role=dialog]');
        const top = (sel) => d.querySelector(sel).getBoundingClientRect().top;
        const head = (name) => [...d.querySelectorAll('h2, h3, h4')].find((h) => h.textContent.trim() === name).getBoundingClientRect().top;
        return [top('[data-room-count]'), top('[data-room-exit]'), head('People'), head('Signal'), head('Live signal'), head('Temperature and humidity')] }""")
    assert tops == sorted(tops), tops
    assert "room=room2" in page.url
    small = page.evaluate(SMALL_TEXT, "[role=dialog]")
    assert not small, f"text under 14 px in the room panel: {small}"
    page.keyboard.press("Escape")
    drawer.wait_for(state="detached")
    assert not page.errors


def test_room_without_a_sensor_says_so(server, page):
    url, _ = server
    page.goto(url + "/floor?room=room3")
    drawer = page.get_by_role("dialog")
    drawer.get_by_role("heading", name="Room 3").wait_for()
    box = drawer.locator("[data-no-sensor]")
    box.get_by_text("No sensor", exact=True).wait_for()
    assert "dashed" in box.evaluate("e => getComputedStyle(e).borderStyle")
    assert drawer.locator("[data-pair]").count() == 0
    assert not page.errors


def test_switch_floor_and_back(server, page):
    """The building chip opens the switcher; typing "level 7" and Enter shows the example building's Level 7 on the
    Overview, the Floor plan and Rooms, marked as example data with every room "No sensor"; a refresh keeps it; the
    rail's icon opens the same panel; switching back shows the demo floor again."""
    url, _ = server
    push(url, "room1", 0.2)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(url + "/")
    page.locator("[data-room=room1]").first.wait_for()
    chip = page.locator("#sidebar [data-building]")
    assert chip.get_attribute("aria-haspopup") == "dialog"
    chip.click()
    panel = page.get_by_role("dialog", name="Change building or floor")
    # a wide panel beside the sidebar: buildings on the left, the highlighted building's floors on the right
    panel.get_by_role("listbox", name="Buildings").wait_for()
    side, box = page.locator("#sidebar").bounding_box(), panel.bounding_box()
    assert box["x"] >= side["x"] + side["width"] and box["width"] >= 600, (side, box)
    page.keyboard.press("ArrowDown")  # the example building: its floors show on the right
    panel.get_by_role("listbox", name="Floors of Example Tower (example data)").wait_for()
    page.keyboard.press("ArrowUp")
    panel.get_by_role("listbox", name="Floors of Demo Building").wait_for()
    panel.get_by_role("combobox", name="Search building, code or floor").fill("level 7")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"[?&]floor=ex-7"))
    assert not panel.is_visible()
    page.locator("[data-example-note]").filter(has_text="Example data: this building has no sensors.").wait_for()
    page.get_by_text("Room 7.01").first.wait_for()
    assert page.locator("[data-room=room1]").count() == 0  # the demo floor's rooms are not drawn here
    assert "Example Tower (example data), Level 7" in page.locator("main").inner_text()
    assert page.get_by_text("No sensor").count() >= 8
    page.reload()
    page.get_by_text("Room 7.01").first.wait_for()  # a refresh keeps the floor
    page.locator("#sidebar").get_by_role("link", name="Floor plan").click()
    page.get_by_role("heading", name=re.compile("Level 7")).first.wait_for()
    page.locator("[data-example-note]").wait_for()
    page.locator("#sidebar").get_by_role("link", name="Rooms").click()
    page.locator("[data-example-note]").wait_for()
    assert page.locator("tbody tr", has_text="Lab 2").count() == 0  # the rooms of this floor only
    page.locator("[data-menu]").click()  # fold the sidebar to the rail: its building icon opens the same panel
    page.locator("[data-sidebar=rail]").wait_for()
    page.locator("#sidebar [data-building]").click()
    panel.wait_for()
    panel.get_by_role("combobox", name="Search building, code or floor").fill("demo")
    panel.get_by_role("option", name=re.compile("Level 4")).click()
    page.goto(url + "/")
    page.locator("[data-room=room1]").first.wait_for()
    assert page.locator("[data-example-note]").count() == 0
    small = page.evaluate(SMALL_TEXT, "body")
    assert not small, f"text under 14 px: {small}"
    assert not page.errors


def canvas_click(page, x, y):
    """A point of the plan (1000 x 560 units) on the editor's canvas, in page pixels (the canvas scrolled into view)."""
    canvas = page.locator("[data-editor-canvas]")
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    return box["x"] + x / 1000 * box["width"], box["y"] + y / 560 * box["height"]


def test_draw_a_room_save_it_and_restore_the_plan_before(server, page):
    """An admin opens the editor from the Floor plan page, makes room by removing the pantry, draws a room, names it,
    gives it an ID and an exit, places its sensor pair and sees the guideline; a room drawn into another is listed as
    a problem and Save stays off; the save becomes version 1 and the Overview draws the room; restoring the built-in
    plan makes version 2 and the room goes; the audit log has both."""
    url, _ = server
    push(url, "room1", 0.2)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto(url + "/floor")
    page.locator("[data-edit-plan]").click()
    page.wait_for_url(re.compile(r"/floor/edit\?floor=f1"))
    page.locator("[data-editor-canvas]").wait_for()
    page.get_by_text("No problems found").wait_for()
    shapes = page.locator("[data-shape-list]")
    shapes.get_by_role("button", name=re.compile("^Pantry")).click()
    page.get_by_role("button", name="Remove this shape").click()
    # draw a room where the pantry was
    # every group of the toolbar has its label, and at this width (wide enough for one row) they share a baseline
    assert page.get_by_role("radiogroup", name="Draw").get_by_role("radio").count() == 4
    page.get_by_role("group", name="Background image").get_by_text("PNG or JPG, up to 2 MB").wait_for()
    labels = page.locator("[data-toolbar-group] > :first-child")
    assert [t.strip() for t in labels.all_inner_texts()] == ["Draw", "Start from", "Background image"]
    assert len({round(box["y"]) for box in (labels.nth(i).bounding_box() for i in range(3))}) == 1
    page.get_by_role("radio", name="Room").click()
    x1, y1 = canvas_click(page, 640, 330)
    x2, y2 = canvas_click(page, 840, 520)
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move((x1 + x2) / 2, (y1 + y2) / 2, steps=4)
    page.mouse.move(x2, y2, steps=4)
    page.mouse.up()
    room_id = page.get_by_role("textbox", name="Room ID (what the sensors report)")
    room_id.wait_for()
    room_id.fill("lab9")
    page.get_by_role("textbox", name="Name").fill("Lab 9")
    page.get_by_role("combobox", name="Nearest exit").select_option(label="Stair B")
    page.get_by_role("spinbutton", name="Area in m²").fill("48")
    page.get_by_role("spinbutton", name="Capacity (people), optional").fill("12")
    assert "suggested sensor pairs: 3" in page.locator("[data-guideline]").inner_text()
    page.get_by_role("button", name="Place").click()
    page.mouse.click(*canvas_click(page, 670, 480))
    page.mouse.click(*canvas_click(page, 810, 480))
    assert page.locator("[data-pair]").inner_text().find("Sender and receiver drawn.") >= 0
    page.get_by_text("No problems found").wait_for()
    # into Lab 2: listed as a problem, Save off; then back
    y = page.get_by_role("spinbutton", name="Y", exact=True)
    y.fill("100")
    page.locator("[data-checks]").get_by_role("button", name="Lab 2 and Lab 9 overlap.").wait_for()
    assert page.get_by_role("button", name="Save...").is_disabled()
    y.fill("330")
    page.get_by_text("No problems found").wait_for()
    page.get_by_role("button", name="Save...").click()
    dialog = page.get_by_role("dialog", name="Save this plan as a new version?")
    assert "1 room added" in dialog.locator("[data-save-summary]").inner_text()
    dialog.get_by_role("textbox", name="Note").fill("Lab 9 opened")
    dialog.get_by_role("button", name="Save").click()
    page.get_by_role("status").filter(has_text="Saved as version 1.").wait_for()
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px in the editor: {small}"
    # the Overview draws the new room, with its sensor pair and no report yet
    page.goto(url + "/")
    tile = page.locator("[data-room=lab9]").first
    tile.wait_for()
    assert "Lab 9" in tile.inner_text() and "No report yet" in tile.inner_text()
    info = page.request.get(url + "/api/info").json()
    assert info["room_floors"]["lab9"] == "f1" and info["room_exits"]["lab9"] == "Stair B"
    # restore the built-in plan
    page.goto(url + "/floor/edit?floor=f1")
    versions = page.locator("[data-versions]")
    versions.locator("[data-version='0']").get_by_role("button", name="Restore this version").click()
    page.get_by_role("dialog", name="Restore version 0?").get_by_role("button", name="Restore this version").click()
    page.get_by_role("status").filter(has_text="Version 0 restored as version 2.").wait_for()
    page.goto(url + "/")
    page.locator("[data-room=room1]").first.wait_for()
    assert page.locator("[data-room=lab9]").count() == 0
    page.goto(url + "/alerts")
    audit = page.locator("[data-audit]")
    audit.get_by_text("Floor plan restored").first.wait_for()
    audit.get_by_text("Floor plan saved").first.wait_for()
    # the capacity set on the new room is in the log of the save, and its removal in the log of the restore
    lines = audit.locator("[data-audit-capacity] li").all_inner_texts()
    assert any("lab9" in line and "12" in line for line in lines), lines
    assert not page.errors


def test_overview_select_a_room_refresh_and_open_it(server, page):
    """A click on the plan selects a room: the tile is marked, the People card follows, the address and the browser
    keep the choice across a refresh, and a double-click opens the room's panel. The card's range goes to the address
    and stays after a refresh. However many rooms report, the overview asks for the signals in one request and never
    per room."""
    url, _ = server
    for room_id in ("room1", "room2"):
        push(url, room_id, 0.2)
    asked = []
    page.on("request", lambda r: asked.append(r.url))
    page.goto(url + "/")
    page.get_by_role("group", name="Floor plan").wait_for()
    first = page.get_by_role("button", name=re.compile("^Lab 2"))
    select = page.get_by_role("combobox", name="Room shown")
    page.wait_for_function("document.querySelector('[data-people-room]').value === 'room1'")
    card = page.get_by_role("region", name="People")
    card.locator("[data-people-chart='1h']").wait_for()  # the default range, drawn from this room's stored reports
    assert re.match(r"Now 0", card.locator("[data-people-now]").inner_text())
    card.get_by_role("combobox", name="Time range").select_option("7d")  # a compact select at this width
    page.wait_for_url(re.compile(r"[?&]range=7d"))
    card.locator("[data-people-chart='7d']").wait_for()
    page.reload()
    page.get_by_role("region", name="People").locator("[data-people-chart='7d']").wait_for()
    page.get_by_role("region", name="People").get_by_role("combobox", name="Time range").select_option("1h")
    page.wait_for_url(re.compile(r"[?&]range=1h"))  # a choice made by hand is written, the default too
    assert first.get_attribute("aria-pressed") == "true"  # the default: the live room with its boards on the plan
    assert "room=" not in page.url                        # the default is not written to the address
    # a room with no sensor: the card says so in words, with no chart
    none = page.get_by_role("button", name="Room 3: no sensor")
    none.click()
    page.wait_for_url(re.compile(r"[?&]room=room3"))
    assert none.get_attribute("aria-pressed") == "true" and first.get_attribute("aria-pressed") == "false"
    assert none.locator("[data-selected-tab]").count() == 1
    assert select.input_value() == "room3"
    card.locator("[data-people-none=no_sensor]").wait_for()
    assert card.locator("[data-people-chart]").count() == 0
    page.reload()
    page.get_by_role("button", name="Room 3: no sensor").wait_for()
    assert page.get_by_role("button", name="Room 3: no sensor").get_attribute("aria-pressed") == "true"
    page.goto(url + "/")  # the address cleared: the last choice comes back from this browser
    page.get_by_role("button", name="Room 3: no sensor").wait_for()
    assert page.get_by_role("button", name="Room 3: no sensor").get_attribute("aria-pressed") == "true"
    # keyboard: Enter on a tile selects it, the dropdown shows the same room
    hall = page.get_by_role("button", name=re.compile("^Hall A"))
    hall.focus()
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"[?&]room=room2"))
    assert hall.get_attribute("aria-pressed") == "true" and select.input_value() == "room2"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px on the overview: {small}"
    assert any("/api/signals" in u for u in asked), asked
    assert not [u for u in asked if re.search(r"/api/rooms/[^/]+/signal", u)], "the overview asked for one room's signal"
    assert any("view=people" in u and "room=room1" in u for u in asked), "the People card did not ask for the room's people"
    hall.dblclick()
    page.wait_for_url(re.compile(r"/floor\?room=room2$"))
    page.get_by_role("dialog").get_by_role("heading", name="People").wait_for()
    assert not page.errors


def test_overview_feeds_show_whole_rows_and_link_to_the_rest(server, page):
    """Thirteen alerts and thirteen rooms that need attention: the feeds draw whole rows only (no scroll box, no half
    row), "View all 13" opens the full list, and the cards around them stay where they were."""
    url, _ = server
    push(url, "room1", 0.2)
    page.goto(url + "/")
    page.locator("[data-people-room]").wait_for()
    place = "() => { const b = document.querySelector('[data-people-room]').closest('section').getBoundingClientRect(); return [b.top, b.left] }"
    before = page.evaluate(place)
    now = int(time.time())

    def thirteen(route):
        answer = route.fetch()
        body = answer.json()
        body["alerts"] = [{"id": f"x{i}", "ts": now - i * 60, "kind": "info", "severity": "info", "via": "console", "subject": f"NADI: Test alert {i}",
                           "message": "A long line of text that takes two lines in a narrow card, to make every row as tall as rows get.", "ack": None,
                           "drill": False} for i in range(13)]
        body["rooms"] = [{"room_id": f"x{i:02d}", "name": f"Extra {i + 1}", "headcount": 0, "at_least": False, "counter": "csi", "count_ts": now - 3,
                          "temp_c": 23.0, "humidity": 60, "live": True, "waste": {"since": now - 840, "minutes": 14, "rm": 0.7}} for i in range(13)]
        route.fulfill(response=answer, json=body)

    page.route("**/api/rooms?*", thirteen)
    page.reload()
    page.get_by_role("link", name="View all 13").first.wait_for()
    whole = """(sel) => { const list = document.querySelector(sel); const box = list.parentElement.getBoundingClientRect();
        const rows = [...list.children].filter((r) => r.getClientRects().length);
        return { shown: rows.length, cut: rows.filter((r) => r.getBoundingClientRect().bottom > box.bottom + 1).length,
                 overflow: getComputedStyle(list.parentElement).overflowY } }"""
    for sel in ("[data-activity]", "[data-attention]"):
        got = page.evaluate(whole, sel)
        assert 1 <= got["shown"] <= 10 and got["cut"] == 0 and got["overflow"] == "hidden", f"{sel}: {got}"
    assert page.evaluate(place) == before, "the People card moved when the lists got longer"
    assert page.locator("[data-off-plan]").inner_text().count("Extra") == 10  # ten names, then a link to the rest
    assert page.locator("[data-off-plan-more]").inner_text() == "and 3 more"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    queue = page.get_by_role("region", name="Needs attention")
    queue.get_by_role("link", name="View all 13").click()
    page.wait_for_url(re.compile(r"/alerts#attention$"))
    page.wait_for_function("document.querySelectorAll('#attention [data-attention] > li').length === 13")  # the full queue
    page.get_by_role("heading", name="Needs attention now").wait_for()
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px on the alerts page: {small}"
    assert not page.errors


def test_energy_settings_edit_save_and_put_back(server, page):
    """An admin changes the waste delay on the Energy page: the change is listed before it is stored, the card shows
    the new value and who changed it, the history and the audit log have it, and the Rooms page follows. The value is
    put back at the end, so the next run starts from the same place."""
    url, _ = server
    before = page.request.get(url + "/api/energy/settings").json()["settings"]
    delay = 2 if before["waste_after_min"] == 1 else 1
    page.goto(url + "/energy")
    card = page.get_by_role("region", name="Energy settings")
    card.get_by_role("button", name="Edit").click()
    field = card.get_by_role("textbox", name="Waste flagged after")
    field.fill("0")
    card.get_by_role("button", name="Save").click()
    card.get_by_role("alert").filter(has_text="Waste flagged after must be between 1 and 240 minutes.").wait_for()
    field.fill(str(delay))
    card.get_by_role("button", name="Save").click()
    dialog = page.get_by_role("dialog", name="Save these changes?")
    old = "1 minute" if before["waste_after_min"] == 1 else f"{before['waste_after_min']:g} minutes"
    new = "1 minute" if delay == 1 else f"{delay} minutes"
    assert dialog.get_by_role("listitem").all_inner_texts() == [f"Waste flagged after: {old} → {new}"]
    dialog.get_by_role("button", name="Save").click()
    card.get_by_role("status").filter(has_text="Saved. The new values apply from").wait_for()
    shown = f"{delay}"  # the tile shows the number; the unit sits beside it
    assert card.locator('[data-setting="waste_after_min"] [data-value]').inner_text() == shown
    assert "Last changed by localhost on" in card.locator("[data-settings-source]").inner_text()
    card.get_by_role("button", name="History").click()  # the change history opens in a side panel
    history = page.get_by_role("dialog", name="Change history")
    assert f"Waste flagged after: {old} → {new}" in history.locator("tbody tr").first.inner_text()
    page.keyboard.press("Escape")
    assert page.request.get(url + "/api/info").json()["waste_minutes"] == delay
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px on the energy page: {small}"
    page.goto(url + "/alerts")
    page.locator("[data-audit-changes]").first.filter(has_text=f"Waste flagged after: {old} → {new}").wait_for()
    # put it back through the same API the card uses (from this computer, same origin)
    back = page.request.put(url + "/api/energy/settings", data=before)
    assert back.ok and back.json()["settings"] == before
    assert not page.errors


def test_todays_summary_page(server, page):
    """"View full summary" on the overview opens the day's summary: a row per reporting room, today's emergencies and
    drills, the way back, and nothing under 14 px."""
    url, _ = server
    push(url, "room1", 0.2)
    page.goto(url + "/")
    page.get_by_role("link", name="View full summary").click()
    page.wait_for_url(re.compile(r"/summary$"))
    page.get_by_role("heading", name="Today's summary", level=1).wait_for()
    rows = page.locator("[data-summary-rooms] tbody tr")
    rows.first.wait_for()
    assert page.locator("[data-summary-rooms] [data-room=room1]").count() == 1
    page.get_by_role("heading", name="Emergencies and drills today").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px on the summary: {small}"
    page.get_by_role("link", name="Building summary").click()
    page.get_by_role("heading", name="Building summary", level=1).wait_for()
    assert not page.errors


def test_overview_links_to_the_room_details(server, page):
    """"Room details" on the People card opens the room's panel; an older link with section=signal still opens the
    panel at its Signal section."""
    url, _ = server
    push(url, "room1", 0.2)
    page.goto(url + "/")
    link = page.get_by_role("link", name="Room details")
    assert link.get_attribute("href") == "/floor?room=room1"
    link.click()
    page.wait_for_url(re.compile(r"/floor\?room=room1$"))
    drawer = page.get_by_role("dialog")
    drawer.get_by_role("heading", name="People").wait_for()
    page.goto(url + "/floor?room=room1&section=signal")
    page.get_by_role("dialog").get_by_role("heading", name="Signal", exact=True).wait_for()
    page.wait_for_function("() => { const h = document.getElementById('room-signal'); const d = h.closest('[role=dialog]');"
                           " return h.getBoundingClientRect().top - d.getBoundingClientRect().top < 120 }")
    assert not page.errors


def test_people_history_and_energy_by_room_from_the_database(server, page):
    """The people chart's answer and the Energy page's room list come from MySQL as stored: every range answers with
    its bucket, an unknown room is refused, and the Energy page lists each room with RM, kWh and hours and filters
    its chart to a room from the address."""
    url, _ = server
    push(url, "room1", 0.2)
    for minutes, bucket in ((60, 60), (1440, 1800), (10080, 10800), (43200, 86400)):
        got = page.request.get(f"{url}/api/history?room=room1&view=people&minutes={minutes}")
        assert got.status == 200, got.text()
        body = got.json()
        assert body["bucket_s"] == bucket and body["room_id"] == "room1" and body["people"], body
        assert all(len(point) == 3 and point[1] >= 0 and 0 <= point[2] <= bucket // 60 for point in body["people"]), body["people"][:5]
        assert [point[0] for point in body["people"]] == sorted(point[0] for point in body["people"])
        assert body["since"] is None or set(body["since"]) == {"occupied", "ts"}
    assert page.request.get(url + "/api/history?room=nope&view=people").status == 422
    assert page.request.get(url + "/api/history?view=people").status == 422
    assert page.request.get(url + "/api/energy?range=7d&room=nope").status == 422
    energy = page.request.get(url + "/api/energy?range=7d&room=room1").json()["range"]
    assert energy["series_room"] == "room1" and len(energy["series"]["points"]) == 7
    assert all(set(r) >= {"room_id", "name", "rm", "kwh", "hours"} for r in energy["by_room"]), energy["by_room"]
    page.goto(url + "/energy?range=7d&room=room1")
    chip = page.locator("[data-room-chip]")
    chip.wait_for()
    assert chip.inner_text().strip() == "Lab 2"
    table = page.locator("[data-by-room]")
    table.locator("tbody tr[data-room=room1]").wait_for()
    assert [h.strip() for h in table.get_by_role("columnheader").all_inner_texts()] == ["Room", "Wasted", "kWh", "Hours"]
    chip.get_by_role("button", name="Show the whole building").click()
    page.wait_for_function("() => !location.search.includes('room=')")
    assert page.locator("[data-room-chip]").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    small = page.evaluate(SMALL_TEXT, "#main")
    assert not small, f"text under 14 px on the energy page: {small}"
    assert not page.errors


def test_calibration_page(server, page):
    """The old /label address opens Calibration: the NADI logo, which detector is live (never MindSpore unless the
    server says a model is counting), the model's true state and the labelled reports, admin only. The two columns
    end on the same line at both sizes, the live detector lies across the page below them, and thirteen labels show
    as ten rows that open inside the card."""
    url, tmp = server
    detector = page.request.get(url + "/api/detector").json()
    page.goto(url + "/label")
    page.wait_for_url(re.compile("/calibration"))
    page.get_by_role("heading", name="Calibration", level=1).wait_for()
    assert page.locator("[data-logo]").count() == 2 and page.locator("header [data-logo=light]").is_visible()
    page.locator("[data-live-chip]").wait_for()  # inside the normal frame, with the same page header as the rest
    page.locator("#sidebar").get_by_role("link", name="Calibration").wait_for()
    table = page.locator("[data-detector]")
    table.get_by_role("heading", name="Live detector").wait_for()
    counting = table.locator("tbody tr[data-room=room1] td").first.inner_text()
    if detector["mode"] == "rule":
        assert counting == "Calibrated rule", counting
        assert re.fullmatch(r"[0-9.]+ dB", table.locator("tbody tr[data-room=room1] td").nth(1).inner_text())
        assert "MindSpore" not in table.locator("tbody").inner_text()
    else:
        assert counting == "MindSpore model"
    assert table.locator("tbody tr[data-room=room3] td").first.inner_text() == "No sensor"  # every room, with or without a sensor
    page.get_by_role("heading", name="Model training · Huawei MindSpore").wait_for()
    status = page.locator("[data-model-status]").first.inner_text()
    assert status.startswith("Active") == bool(detector["model"] and detector["model"]["active"]), status
    page.get_by_role("heading", name="Labelled reports").wait_for()
    card = page.get_by_role("region", name="Label headcount")
    card.get_by_role("combobox", name="Room").wait_for()
    assert card.locator("[data-segmented] button").all_inner_texts() == ["0", "1", "2", "3", "4", "5"]
    # thirteen labels: ten rows and "Show 3 more"; opened, they scroll inside the card, which stops growing.
    # Twelve of them are written straight into this server's labels file (yesterday's, so they touch no report):
    # thirteen taps in a row would run into the limit on admin requests per minute.
    start = int(time.time()) - 86400
    (tmp / "labels.csv").write_text("room_id,start_ts,end_ts,headcount\n" + "".join(
        f"room1,{start + i * 100},{start + i * 100 + 60},{i % 2}\n" for i in range(12)), encoding="utf-8")
    page.reload()
    card.locator("[data-segmented] button").nth(1).click()
    card.get_by_role("button", name="Stop").click()
    more = card.get_by_role("button", name="Show 3 more")
    more.wait_for()
    more.click()
    page.wait_for_function("document.querySelectorAll('[data-recent-labels] tbody tr').length === 13")
    box = page.evaluate("(() => { const b = document.querySelector('[data-recent-labels]').parentElement;"
                        " return { h: b.clientHeight, inner: b.scrollHeight, rem: parseFloat(getComputedStyle(document.documentElement).fontSize) } })()")
    assert box["h"] <= 26 * box["rem"] + 1 and box["inner"] > box["h"], box  # a fixed maximum height, the rest scrolls inside
    card.get_by_role("button", name="Show fewer").click()
    page.wait_for_function("document.querySelectorAll('[data-recent-labels] tbody tr').length === 10")
    bottoms = """() => { const c = document.querySelector('[data-cal-columns]'); const l = c.children[0].getBoundingClientRect();
        const r = [...c.children[1].querySelectorAll('section')].pop().getBoundingClientRect();
        const d = document.querySelector('[data-detector]').getBoundingClientRect();
        return { left: l.bottom, right: r.bottom, below: d.top, span: d.width, cols: c.getBoundingClientRect().width, side: l.right <= r.left } }"""
    for width, height in ((1366, 768), (1920, 1080)):
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(300)
        b = page.evaluate(bottoms)
        assert b["side"], f"one column at {width} px: {b}"
        assert abs(b["left"] - b["right"]) <= 1, f"the two columns do not end on one line at {width} px: {b}"
        assert b["below"] >= b["left"] and abs(b["span"] - b["cols"]) <= 1, f"live detector not across the page at {width} px: {b}"
    page.set_viewport_size({"width": 1366, "height": 768})
    small = page.evaluate(SMALL_TEXT, "body")
    assert not small, f"text under 14 px on the calibration page: {small}"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    far = page.request.get(url + "/api/detector", headers={"Host": "nadi.example"})
    assert far.status in (401, 403)  # only this computer counts as admin when no token is set
    assert not page.errors


def test_start_and_end_emergency(server, page):
    url, _ = server
    page.goto(url + "/rooms")
    page.get_by_role("button", name="Start emergency mode").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Start emergency mode").click()
    takeover = page.get_by_role("alertdialog", name="Emergency mode")
    takeover.wait_for()
    takeover.get_by_text("people still inside").wait_for()
    takeover.get_by_role("heading", name="Go here first").wait_for()
    takeover.get_by_role("button", name="End emergency mode").click()
    takeover.get_by_role("button", name="End emergency mode on every screen").click()
    takeover.wait_for(state="detached", timeout=10000)
    assert not page.errors


def test_drill_with_warden_marks_export_and_report(server, page, browser):
    """A drill: DRILL banner, a warden marks a room, the export shows the mark, ending it writes a report that is
    listed apart from real incidents on the Alerts page. It is started from the example building, and the full-screen
    view still draws the floor whose rooms report, never the example one."""
    url, tmp = server
    push(url, "room1", 0.2)
    page.goto(url + "/?floor=ex-3")
    page.locator("[data-example-note]").wait_for()
    page.get_by_role("button", name="Start emergency mode").first.click()
    page.get_by_role("dialog").get_by_role("button", name="Start drill").click()
    takeover = page.get_by_role("alertdialog", name="Drill")
    takeover.locator("svg[role=group]").wait_for()
    drawn = takeover.locator("svg[role=group]").text_content()
    assert "Lab 2" in drawn and "Room 3.01" not in drawn, drawn
    takeover.wait_for()
    takeover.get_by_text("DRILL: this is a practice run, not a real emergency.").wait_for()
    takeover.get_by_role("button", name="Searched, clear").first.click()
    takeover.get_by_text("Searched, clear (localhost").first.wait_for()
    export = browser.new_page(viewport={"width": 1366, "height": 768})
    export.goto(url + "/export")
    export.get_by_text("Searched, clear (localhost").first.wait_for()
    export.get_by_text("DRILL: this is a practice run, not a real emergency.").wait_for()
    export.close()
    snaps = list((tmp / "incidents").glob("*-drill-*/latest.en.html"))
    assert snaps, "the first snapshot is saved as soon as the drill starts"
    takeover.get_by_role("button", name="End drill").click()
    takeover.get_by_role("button", name="End the drill on every screen").click()
    takeover.wait_for(state="detached", timeout=10000)
    page.goto(url + "/alerts")
    reports = page.get_by_role("region", name="Incident and drill reports")
    reports.locator("table").last.get_by_role("link", name="Open").first.click()  # the Drills table, after real incidents
    page.get_by_text("Drill report").wait_for()
    page.get_by_text("Searched, clear (localhost").first.wait_for()
    assert not page.errors


def test_chat_in_english_and_malay(server, page):
    url, _ = server
    push(url, "room1", 0.2)  # a live room, so the answers are about readings and not "no live data"
    page.goto(url + "/")
    page.get_by_role("button", name="Open Ask NADI").click()
    panel = page.get_by_role("dialog", name="Ask NADI")
    chips = panel.locator("[data-suggestions] button")
    assert chips.all_inner_texts() == ["How many people are inside?", "Which rooms waste air conditioning?", "Bilik mana ada orang?"]
    # the answer itself, not the "Checking the live readings" bubble shown while it is on its way
    done = "n => document.querySelectorAll('[data-ask-panel] [data-line=a]').length >= n"
    chips.nth(1).click()  # a suggested question is sent as it is
    page.wait_for_function(done, arg=1, timeout=20000)
    assert panel.locator("[data-line=q]").inner_text().endswith("Which rooms waste air conditioning?")
    waste = panel.locator("[data-line=a]").nth(0).inner_text()
    assert "air conditioning" in waste.lower(), waste
    # the scope chip: this floor by default, and every answer starts with its scope
    assert panel.get_by_role("radio", name="This floor: Level 4").get_attribute("aria-checked") == "true"
    assert waste.split(": ", 1)[-1] and "Level 4: " in waste, waste
    assert panel.locator("[data-suggestions]").count() == 0
    panel.get_by_label("Question").fill("Which rooms are empty?")
    panel.get_by_label("Question").press("Enter")
    page.wait_for_function(done, arg=2, timeout=20000)
    english = panel.locator("[data-line=a]").nth(1).inner_text()
    assert "empty" in english.lower() or "kosong" not in english.lower()
    panel.get_by_label("Question").fill("Berapa orang di dalam?")
    panel.get_by_label("Question").press("Enter")
    page.wait_for_function(done, arg=3, timeout=20000)
    malay = panel.locator("[data-line=a]").nth(2).inner_text()
    assert "orang" in malay.lower() or "tiada" in malay.lower(), malay
    assert "Level 4: " in malay, malay  # the floor's name, as written


def test_label_a_room_on_a_phone(server, browser):
    url, tmp = server
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(url + "/label")  # the old address still works: it opens the calibration page
    pg.wait_for_url(re.compile("/calibration"))
    card = pg.get_by_role("region", name="Label headcount")
    card.get_by_role("combobox", name="Room").select_option("room1")
    card.get_by_role("group", name="People in the room now").get_by_role("button", name="1", exact=True).click()
    pg.get_by_role("status").filter(has_text="Saved: Lab 2, 1").wait_for()
    rows = list(csv.DictReader(open(tmp / "labels.csv", encoding="utf-8")))
    assert rows[-1]["room_id"] == "room1" and rows[-1]["headcount"] == "1" and rows[-1]["end_ts"] == ""
    assert card.locator("[data-recent-labels] tbody tr").first.inner_text().split()[:3] == ["Lab", "2", "1"]
    pg.get_by_role("button", name="Undo last").click()
    pg.get_by_role("status").filter(has_text="Last label removed").wait_for()
    assert not pg.evaluate(SMALL_TEXT, "body")
    assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ctx.close()


def test_demo_scenario_runs_to_all_clear(tmp_path, browser):
    proc = start_server(8032, tmp_path, DEMO_SCENARIO="on")
    try:
        url = "http://127.0.0.1:8032"
        time.sleep(3)
        req = urllib.request.Request(url + "/api/demo/restart", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        ctx = browser.new_context(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
        pg = ctx.new_page()
        pg.goto(url + "/")
        pg.get_by_text("DEMO SCENARIO").first.wait_for()
        pg.get_by_role("alertdialog", name="Emergency mode").wait_for(timeout=150000)  # alarm at 2:00
        pg.get_by_role("alertdialog").get_by_text("DEMO SCENARIO").wait_for()
        pg.get_by_role("alertdialog", name="Emergency mode").wait_for(state="detached", timeout=60000)  # all clear at 2:45
        pg.goto(url + "/alerts")
        pg.get_by_text("Emergency mode ended by demo").first.wait_for()
        ctx.close()
    finally:
        proc.terminate()
        proc.wait(10)


def test_viewer_token_screen(browser, tmp_path):
    """VIEWER_TOKEN set and the server computer not counted as admin: the console asks for the token first, a wrong one
    is refused, the right one opens it, and the emergency view carries the safety note."""
    token = "viewer-e2e-0123456789abcdef"
    proc = start_server(8033, tmp_path, VIEWER_TOKEN=token, LOCALHOST_ADMIN="off")
    try:
        ctx = browser.new_context(viewport={"width": 1366, "height": 768})
        pg = ctx.new_page()
        pg.goto("http://127.0.0.1:8033/")
        pg.get_by_role("heading", name="Viewer sign-in").wait_for()
        pg.get_by_label("Viewer token").fill("wrong-token-0123456789")
        pg.get_by_role("button", name="Sign in").click()
        pg.get_by_role("alert").get_by_text("That token is not accepted.").wait_for()
        pg.get_by_label("Viewer token").fill(token)
        pg.get_by_role("button", name="Sign in").click()
        pg.get_by_role("heading", name="Building summary").wait_for()
        pg.get_by_role("button", name="Sign out of the dashboard").wait_for()
        pg.goto("http://127.0.0.1:8033/export")
        pg.get_by_text("NADI snapshot for emergency services").wait_for()
        pg.get_by_text("Emergency number: 999 (112 from a mobile phone)").wait_for()
        pg.get_by_text("NADI assists rescuers; it does not replace a physical sweep.").wait_for()
        ctx.close()
    finally:
        proc.terminate()
        proc.wait(10)
