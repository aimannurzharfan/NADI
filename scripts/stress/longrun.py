"""Long run: the dashboard open for 30 minutes with the simulator running, in headless Chromium (Playwright).

Every minute: force garbage collection, then record the JS heap, DOM node count, alert items and chat log lines.
Both capped lists (6 alerts on the overview, 40 chat lines) are filled before measuring starts; then it keeps asking a chat question
every 20 s and toggling emergency mode every 2 minutes (each toggle adds alerts), so new items keep pushing old ones out.
PASS: heap after the first 5 minutes grows less than 20%, DOM nodes stay within 10%, overview alerts <= 6, chat <= 40.
The emergency screen adds about 180 elements while it is up, so DOM nodes are compared screen by screen (emergency
screen up or not, recorded with each sample), never one screen against the other.

    python scripts/stress/longrun.py [--minutes 30]
"""
import argparse
import statistics
import time

from common import HEADERS, Server, request, save, start_sim

PORT = 8003


def sample(page, cdp):
    cdp.send("HeapProfiler.collectGarbage")
    heap = cdp.send("Runtime.getHeapUsage")["usedSize"]
    return {
        "heap_mb": round(heap / 2**20, 2),
        "dom_nodes": page.evaluate("document.getElementsByTagName('*').length"),
        "emergency_view": page.evaluate("document.querySelector('[role=alertdialog]') !== null"),
        "alerts": page.evaluate("document.querySelectorAll('section[aria-label=\"Recent alerts\"] li').length"),
        # messages only: the chat log also holds an empty scroll anchor and, while waiting, a "waiting" bubble
        "chat_lines": page.evaluate("[...document.querySelectorAll('[aria-live=polite] > div')]"
                                    ".filter(d => d.textContent.trim() && !d.classList.contains('w-fit')).length"),
    }


def main(minutes):
    from playwright.sync_api import sync_playwright

    server = Server(port=PORT, name="longrun-server", REPORT_INTERVAL_S=10, CHAT_PER_MIN=100, EMERGENCY_PER_MIN=100).start()
    sim = start_sim(10, "longrun-sim")
    samples, asked, toggles, errors = [], 0, 0, []
    start = time.time()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.on("console", lambda m: m.type == "error" and errors.append(m.text))
            request("POST", server.url + "/api/emergency", {"on": False}, HEADERS)  # left on by a demo or crash
            page.goto(server.url + "/")
            page.evaluate(f"sessionStorage.setItem('nadiAdminToken', '{HEADERS['X-Admin-Token']}')")
            page.reload()
            page.get_by_role("button", name="Ask NADI").click()  # the chat is a slide-over panel: keep it open
            cdp = page.context.new_cdp_session(page)
            # fill both capped lists first, so the measurement shows steady state, not lists filling up
            on = False
            for _ in range(14):
                on = not on
                request("POST", server.url + "/api/emergency", {"on": on}, HEADERS)
            for i in range(22):
                page.get_by_label("Question").fill("How many people are inside?", force=True)
                page.get_by_label("Question").press("Enter")
                page.wait_for_timeout(300)
            page.wait_for_timeout(10000)
            start = time.time()
            next_sample = next_chat = next_toggle = time.time()
            while time.time() - start < minutes * 60:
                now = time.time()
                if now >= next_chat:
                    page.get_by_label("Question").fill(("How many people are inside?", "Bilik mana yang kosong?")[asked % 2], force=True)
                    page.get_by_label("Question").press("Enter")  # works under the emergency overlay too
                    asked += 1
                    next_chat += 20
                if now >= next_toggle and now - start > 30:
                    on = not on
                    request("POST", server.url + "/api/emergency", {"on": on}, HEADERS)
                    toggles += 1
                    next_toggle += 120
                if now >= next_sample:
                    s = sample(page, cdp)
                    s["minute"] = round((now - start) / 60, 1)
                    samples.append(s)
                    print(f"{s['minute']:5.1f} min  heap {s['heap_mb']:6.2f} MB  dom {s['dom_nodes']:5d}  "
                          f"alerts {s['alerts']:2d}  chat {s['chat_lines']:3d}", flush=True)
                    next_sample += 60
                page.wait_for_timeout(1000)
            if on:
                request("POST", server.url + "/api/emergency", {"on": False}, HEADERS)
            browser.close()
    finally:
        sim.terminate()
        server.stop()

    # windows of 8 minutes each hold both screens (emergency mode switches every 2 minutes)
    early = [s for s in samples if 3 <= s["minute"] <= 10]
    late = [s for s in samples if s["minute"] >= minutes - 8]
    heap_early = statistics.median(s["heap_mb"] for s in early)
    heap_late = statistics.median(s["heap_mb"] for s in late)
    dom = {}
    for view in (False, True):
        a = [s["dom_nodes"] for s in early if s["emergency_view"] == view]
        b = [s["dom_nodes"] for s in late if s["emergency_view"] == view]
        if a and b:
            dom["emergency" if view else "dashboard"] = (statistics.median(a), statistics.median(b))
    dom_early = {k: v[0] for k, v in dom.items()}
    dom_late = {k: v[1] for k, v in dom.items()}
    checks = {
        "heap_growth_under_20pct": heap_late <= heap_early * 1.2,
        "dom_nodes_stable": len(dom) == 2 and all(abs(b - a) <= a * 0.1 for a, b in dom.values()),
        "alerts_list_capped_at_6": max(s["alerts"] for s in samples) <= 6,  # overview shows the 6 latest
        "chat_capped_at_40": max(s["chat_lines"] for s in samples) <= 40,
    }
    result = {"minutes": minutes, "questions_asked": asked, "emergency_toggles": toggles,
              "heap_mb_minutes_3_10": heap_early, "heap_mb_last_8": heap_late,
              "dom_nodes_minutes_3_10": dom_early, "dom_nodes_last_8": dom_late,
              "checks": checks, "pass": all(checks.values()), "samples": samples, "console_errors": errors}
    save("longrun", result)
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print(f"heap {heap_early} -> {heap_late} MB, DOM {dom_early} -> {dom_late}, {asked} questions, {toggles} toggles")
    print("LONGRUN", "PASS" if result["pass"] else "FAIL")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    main(ap.parse_args().minutes)
