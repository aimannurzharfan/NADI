"""Broken dependencies and emergency resilience, with the simulator running and the dashboard open (headless).

During an emergency: stop Redis, then MySQL, then Mosquitto, then Ollama, one at a time, and bring each back.
The server must not crash, the dashboard must show a clear banner and recover by itself. Then restart the server
mid-emergency (state and start time must survive), and stop the sensors (rooms keep their last known count, marked).
Added with the incident pass: the snapshot is on disk at once and every minute, also across a server crash; the
sensors stopping raises one critical "sensor stopped" alert during the emergency and one "back online" when they
return; ending writes the incident report with the offline rooms in it.

    python scripts/stress/chaos.py
Needs Docker (redis, mysql, mosquitto from docker-compose.yml). Ollama is restarted only if it was running.
"""
import os
import subprocess
import time
from pathlib import Path

from common import HEADERS, LOGS, ROOT, Server, docker, mysql_count, request, save, start_sim

PORT = 8002
INTERVAL = 10  # sim and server: report every 10 s, sensor offline after 30 s
OLLAMA = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {'' if ok else detail}", flush=True)


def wait_for(fn, timeout, every=1.0):
    """fn() until it returns something truthy, or None after timeout. Returns (value, seconds taken)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            v = fn()
            if v:
                return v, round(time.time() - start, 1)
        except Exception:
            pass
        time.sleep(every)
    return None, round(time.time() - start, 1)


def rooms(url):
    s, body = request("GET", url + "/api/rooms", timeout=5)
    return body if s == 200 else None


def banner(page):
    # the takeover has its own copy of the banner during an emergency: read the visible one
    return page.evaluate("""(() => { const all = [...document.querySelectorAll('[data-offline-banner]')];
      const seen = all.filter(e => e.offsetParent !== null || e.getClientRects().length); return (seen[seen.length - 1] || {textContent: ''}).textContent; })()""")


def ollama_running():
    try:
        s, _ = request("GET", "http://127.0.0.1:11434/api/tags", timeout=2)
        return s == 200
    except Exception:
        return False


def outage(name, service, page, url, banner_text, extra=None):
    """Stop a docker service, check the server copes and the banner shows, start it, check recovery."""
    t_stop = int(time.time())
    docker("stop", service)
    off, took = wait_for(lambda: (r := rooms(url)) and name in r["offline"] and r, 20)
    check(f"{name} down: server answers and reports it offline", off is not None, took)
    shown, took = wait_for(lambda: banner_text in banner(page) and banner(page), 15)
    check(f"{name} down: dashboard banner '{banner_text}...'", shown, banner(page))
    print(f"      banner: {shown}", flush=True)
    page.screenshot(path=str(LOGS / f"chaos-{name}-banner.png"))
    if extra:
        extra(off)
    time.sleep(INTERVAL + 2)  # keep it down across at least one sensor report
    check(f"{name} down: server process still running", SERVER.alive())
    docker("start", service)
    back, took = wait_for(lambda: (r := rooms(url)) and name not in r["offline"] and r, 60)
    check(f"{name} back: recovered on its own", back is not None, took)
    gone, took2 = wait_for(lambda: banner(page) == "" or None, 20)
    check(f"{name} back: banner cleared", gone is not None or banner(page) == "", banner(page))
    print(f"      {name} recovered after {took} s, banner cleared after {took2} s more", flush=True)
    return t_stop


def main():
    global SERVER
    from playwright.sync_api import sync_playwright

    for svc in ("redis", "mysql", "mosquitto"):
        docker("start", svc)
    SERVER = Server(port=PORT, name="chaos-server", REPORT_INTERVAL_S=INTERVAL).start()
    url = SERVER.url
    sim = start_sim(INTERVAL, "chaos-sim")
    had_ollama = ollama_running()
    pw = sync_playwright().start()
    browser = pw.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    try:
        page.goto(url + "/")
        live, took = wait_for(lambda: (r := rooms(url)) and sum(x["live"] for x in r["rooms"]) >= 2 and r, 40)
        check("baseline: simulator data is live", live is not None, took)
        check("baseline: no banner", banner(page) == "", banner(page))

        s, em = request("POST", url + "/api/emergency", {"on": True}, HEADERS)
        since, incident = em.get("since"), em.get("id")
        same = {"on": True, "since": since, "drill": False, "id": incident}
        check("emergency started", s == 200 and em.get("on"), em)
        snaps = LOGS / "incidents" / str(incident)
        check("snapshot saved on disk the moment the emergency started", (snaps / "latest.en.html").is_file(),
              snaps.relative_to(ROOT))  # never the absolute path: it names the user's own folders
        page.wait_for_timeout(6000)
        check("dashboard shows the emergency view", page.locator("[role=alertdialog]").count() == 1)

        # Redis
        def redis_extra(r):
            check("redis down: emergency still shown from last known state", r["emergency"].get("on") and r["stale_ts"])
            s, a = request("POST", url + "/api/chat", {"question": "How many people are inside?"}, HEADERS, timeout=10)
            check("redis down: chat still answers from last known data", s == 200, (s, a))
            check("redis down: dashboard stays in emergency view", page.locator("[role=alertdialog]").count() == 1)
            # fixed one-minute windows: start just after one opens, with a question that never waits for the model
            time.sleep((60 - time.time() % 60) + 0.5 if time.time() % 60 > 45 else 0)
            codes = [request("POST", url + "/api/chat", {"question": "hi"}, {**HEADERS, "X-Forwarded-For": "10.77.0.1"})[0]
                     for _ in range(12)]
            check("redis down: rate limits still enforced (kept in memory meanwhile)", codes[:10] == [200] * 10 and 429 in codes[10:],
                  codes)
        outage("redis", "redis", page, url, "Database offline, showing last known data at", redis_extra)
        r = rooms(url)
        check("redis back: emergency and start time survived the Redis restart",
              r["emergency"] == same, r["emergency"])

        # MySQL
        def mysql_extra(r):
            s, _ = request("GET", url + "/api/history?minutes=30")
            check("mysql down: history answers 503, not 500", s == 503, s)
        t_mysql = outage("mysql", "mysql", page, url, "History database offline since", mysql_extra)
        page.wait_for_timeout((INTERVAL + 2) * 1000)
        n = mysql_count("ts >= %s AND ts <= %s", (t_mysql + 1, t_mysql + INTERVAL + 2))
        check("mysql back: reports made during the outage were written (buffered)", n > 0, n)

        # Mosquitto
        def mqtt_extra(r):
            before = {x["room_id"]: x["count_ts"] for x in r["rooms"]}
            SERVER.mqtt_before = before
        outage("mqtt", "mosquitto", page, url, "Sensor link offline since", mqtt_extra)
        fresh, took = wait_for(lambda: (r := rooms(url)) and any(
            x["count_ts"] and x["count_ts"] > SERVER.mqtt_before.get(x["room_id"], 0) for x in r["rooms"]), 40)
        check("mqtt back: new sensor reports arrive again", fresh is not None, took)

        # Ollama
        if had_ollama:
            subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True)
            wait_for(lambda: not ollama_running(), 10)
            t = time.time()
            s, a = request("POST", url + "/api/chat", {"question": "Which rooms are empty?"}, HEADERS, timeout=15)
            took = round(time.time() - t, 2)
            check("ollama down: chat answers with the built-in checked answer", s == 200 and a.get("source") == "fallback", (s, a))
            # CHAT_TIMEOUT_S (5 s) plus the 0.5 s hard deadline in server/chat.py, plus the request itself
            check("ollama down: first answer within the chat time limit (6 s)", took < 6, took)
            t = time.time()
            s, a = request("POST", url + "/api/chat", {"question": "Which rooms are empty?"}, HEADERS, timeout=15)
            took = round(time.time() - t, 2)
            check("ollama down: next answers at once (no wait after the first failure)",
                  s == 200 and a.get("source") == "fallback" and took < 1, took)
            check("ollama down: server process still running", SERVER.alive())
            log = open(LOGS / "ollama-restart.log", "a", encoding="utf-8")
            subprocess.Popen([str(OLLAMA), "serve"], stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
            up, took = wait_for(ollama_running, 30)
            check("ollama back: running again", up, took)
        else:
            check("ollama: was not running, outage skipped", True)

        # Server restart mid-emergency
        before_kill = len(list(snaps.glob("snapshot-*.json")))
        SERVER.kill()
        down, took = wait_for(lambda: "Server unreachable" in banner(page) and banner(page), 15)
        check("server down: dashboard says the server is unreachable", down, banner(page))
        print(f"      banner: {down}", flush=True)
        SERVER.start()
        r, took = wait_for(lambda: rooms(url), 30)
        check("server restarted mid-emergency: emergency still on with the same start time",
              r and r["emergency"] == same, r and r["emergency"])
        more, took = wait_for(lambda: len(list(snaps.glob("snapshot-*.json"))) > before_kill, 75)
        check("server crashed and restarted: snapshots kept, and saved every minute again", before_kill >= 2 and more, (before_kill, took))
        gone, took = wait_for(lambda: banner(page) == "" or None, 20)
        check("server back: dashboard recovers on its own", gone is not None, banner(page))

        # Sensor offline mid-emergency
        t_stop = int(time.time())
        sim.terminate()
        sim.wait(10)
        stale, took = wait_for(lambda: (r := rooms(url)) and r["rooms"] and all(not x["live"] for x in r["rooms"]) and r,
                               3 * INTERVAL + 25)
        check("sensors offline: rooms marked offline", stale is not None, took)
        if stale:
            check("sensors offline: last known counts kept", all(x["headcount"] is not None for x in stale["rooms"]),
                  [(x["room_id"], x["headcount"]) for x in stale["rooms"]])
        page.wait_for_timeout(6000)
        text = page.locator("[role=alertdialog]").inner_text()
        check("sensors offline: rooms show as unknown with their last known count, never as empty",
              "Unknown now, last known" in text and "?" in text, text[:200])
        check("sensors offline: total says 'at least' and names the unknown rooms", "At least" in text and "unknown" in text, text[:200])
        page.screenshot(path=str(LOGS / "chaos-emergency-offline.png"))

        def stopped_alerts():
            _, body = request("GET", url + "/api/alerts?limit=100")
            return [a for a in body.get("alerts", []) if a["kind"] == "sensor" and a["ts"] >= t_stop]
        found, took = wait_for(lambda: [a for a in stopped_alerts() if "stopped reporting" in a["subject"]], 30)
        check("sensors stopped: a 'sensor stopped' alert, critical during the emergency", found and found[0]["severity"] == "critical",
              found)
        page.wait_for_timeout(12000)  # two more checks of every device: no repeats
        check("sensors stopped: one alert only, no repeats", len([a for a in stopped_alerts() if "stopped" in a["subject"]]) == 1,
              [a["subject"] for a in stopped_alerts()])
        sim = start_sim(INTERVAL, "chaos-sim")
        back, took = wait_for(lambda: [a for a in stopped_alerts() if "back online" in a["subject"]], 45)
        check("sensors back: one 'back online' alert", back is not None and len(back) == 1, (took, back))
        s, _ = request("POST", url + "/api/emergency", {"on": False}, HEADERS)
        rep = request("GET", url + f"/api/incidents/{incident}")[1]
        check("emergency ended: report written, with the rooms that went offline",
              s == 200 and isinstance(rep, dict) and rep.get("kind") == "real" and len(rep.get("offline", [])) >= 1,
              rep if not isinstance(rep, dict) else rep.get("offline"))
    finally:
        request("POST", url + "/api/emergency", {"on": False}, HEADERS)
        browser.close()
        pw.stop()
        if sim.poll() is None:
            sim.terminate()
        SERVER.stop()
        for svc in ("redis", "mysql", "mosquitto"):
            docker("start", svc)
    passed = sum(r["pass"] for r in results)
    save("chaos", {"passed": passed, "total": len(results), "results": results})
    print(f"CHAOS {passed}/{len(results)} passed", "PASS" if passed == len(results) else "FAIL")


if __name__ == "__main__":
    main()
