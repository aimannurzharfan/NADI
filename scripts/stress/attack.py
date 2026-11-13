"""Bad input and abuse against a live server (port 8001), Mosquitto, Redis and MySQL. Prints PASS/FAIL per check.

Covers: oversized, malformed, wrong-type, NaN/Infinity, out-of-range, unknown-room, old/future, duplicate,
SQL-injection, XSS and emoji input over HTTP and MQTT; MQTT without login, with a wrong password, on another
device's topic and for a room the device is not allowed; admin token brute force; chat flood; emergency toggle spam;
two wardens pressing at the same moment; the audit entry in the alerts; XSS in room names on the dashboard.
Added with the security pass: X-Forwarded-For pretending to be this computer; a read flood from one IP (429 with
Retry-After); security headers; headcounts out of range; a board flooding reports; a forged jump in a count; an
oversized MQTT packet; too many broker connections; the viewer token; huawei mode refusing default secrets.
Added with the incident pass: a cross-site POST (CSRF) and a DNS-rebinding Host header against "this computer" admin;
/iotda without INGEST_TOKEN from anywhere but this computer; the API docs; drill mode marked DRILL; warden marks need
the admin token and reset when the drill ends; the report written at the end; data deletion refused without the
token, without the typed phrase and during a drill (a successful deletion is never run here: this is the real data).
Added with the final check: a cross-site POST to /iotda under every spelling of the path (/iotda/, //iotda, /IOTDA);
a second server with an empty INGEST_TOKEN; fake readings that try to show a room as empty during an emergency.

    python scripts/stress/attack.py
The alerts list is restored afterwards; audit entries labelled "stress" are kept (that is the audit log working).
"""
import json
import os
import re
import socket
import subprocess
import threading
import time

from common import (HEADERS, LOGS, PY, ROOT, SIM_DEVICE, TOKEN, Server, mqtt_client, mysql_count, request, save, topic)

PORT = 8001
XSS_NAME = "<img src=x onerror=window.__xss=1>"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")


def rows():
    return mysql_count("room_id IN ('room1','room2','room3') AND ts >= %s", (T0,))


def csi(room="room1", **props):
    return {"service_id": "csi", "properties": {"room_id": room, "ts": 0, "motion_std": 0.2, **props}}


def envelope(services, device="sim-local"):
    return {"resource": "device.property", "notify_data": {"header": {"device_id": device}, "body": {"services": services}}}


def http_bad_input(url):
    iotda = url + "/iotda" + (f"?token={os.environ['INGEST_TOKEN']}" if os.getenv("INGEST_TOKEN") else "")
    now = int(time.time())
    cases = [
        ("oversized body (9 KB)", json.dumps(envelope([csi(pad="x" * 9000)])).encode()),
        ("malformed JSON", b'{"resource": "device.property", "notify_data": {'),
        ("empty body", b""),
        ("wrong type: motion_std as text", envelope([csi(motion_std="abc")])),
        ("NaN", b'{"resource":"device.property","notify_data":{"body":{"services":[{"service_id":"csi","properties":'
                b'{"room_id":"room1","ts":0,"motion_std":NaN}}]}}}'),
        ("Infinity", b'{"resource":"device.property","notify_data":{"body":{"services":[{"service_id":"climate",'
                     b'"properties":{"room_id":"room1","ts":0,"temp_c":Infinity}}]}}}'),
        ("negative motion", envelope([csi(motion_std=-3)])),
        ("temperature 500", envelope([{"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": 500}}])),
        ("humidity 150", envelope([{"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": 24, "humidity": 150}}])),
        ("people 9999 (made-up service)", envelope([{"service_id": "headcount", "properties": {"room_id": "room1", "people": 9999}}])),
        ("count service: 5000 people", envelope([{"service_id": "count", "properties": {"room_id": "room1", "ts": 0, "headcount": 5000}}])),
        ("count service: 2.5 people", envelope([{"service_id": "count", "properties": {"room_id": "room1", "ts": 0, "headcount": 2.5}}])),
        ("count service: negative", envelope([{"service_id": "count", "properties": {"room_id": "room1", "ts": 0, "headcount": -4}}])),
        ("unknown room", envelope([csi("room99")])),
        ("timestamp 2 days old", envelope([csi(ts=now - 2 * 86400)])),
        ("timestamp 1 hour ahead", envelope([csi(ts=now + 3600)])),
        ("SQL injection room id", envelope([csi("room1'; DROP TABLE occupancy;--")])),
        ("XSS room id", envelope([csi("<script>alert(1)</script>")])),
        ("emoji room id", envelope([csi("bilik😀")])),
        ("51 entries", envelope([csi()] * 51)),
        ("services not a list", envelope("nope")),
        ("one bad entry among good ones", envelope([csi("room2"), csi("room3", motion_std=float(1e9))])),
    ]
    before = rows()
    codes = {}
    for name, body in cases:
        status, resp = request("POST", iotda, body if isinstance(body, bytes) else json.dumps(body).encode())
        codes[name] = status
        check(f"HTTP bad input rejected with 4xx: {name}", 400 <= status < 500, f"{status} {resp}")
    check("HTTP bad input: nothing stored", rows() == before, f"{rows() - before} rows added")
    report = envelope([csi("room1", ts=now - 5)])
    s1, r1 = request("POST", iotda, report)
    s2, r2 = request("POST", iotda, report)
    check("valid report stored once", s1 == 200 and r1.get("saved") == 1, r1)
    check("duplicate report accepted but not stored again", s2 == 200 and r2.get("duplicate") == 1 and r2.get("saved") == 0, r2)
    check("duplicate: exactly one row", rows() == before + 1, rows() - before)

    chat = url + "/api/chat"
    s, r = request("POST", chat, {"question": "x" * 501}, HEADERS)
    check("chat question over 500 characters: 422", s == 422, (s, r))
    s, r = request("POST", chat, json.dumps({"question": "x" * 5000}).encode(), HEADERS)
    check("chat body over 4 KB: 413", s == 413, s)
    for q in ("<script>alert(1)</script> how many?", "'; DROP TABLE occupancy;-- berapa orang?", "Berapa orang? 😀🔥"):
        s, r = request("POST", chat, {"question": q}, {**HEADERS, "X-Forwarded-For": "10.66.1.1"})
        check(f"chat odd text answered safely: {q[:20]}", s == 200 and "<script" not in r.get("answer", ""), (s, r))
    s, r = request("POST", url + "/api/emergency", {"on": "false"}, {**HEADERS, "X-Forwarded-For": "10.66.1.2"})
    check('emergency {"on": "false"} as text: 422, alarm not started', s == 422, (s, r))
    return codes


def mqtt_input():
    before = rows()
    c = mqtt_client(SIM_DEVICE)
    check("MQTT simulator login works", c.rc is not None and not c.rc.is_failure, c.rc)
    now = int(time.time())
    bad = [
        b"{not json", b"[1,2,3]", b"null",
        b'{"services":[{"service_id":"csi","properties":{"room_id":"room1","ts":0,"motion_std":NaN}}]}',
        json.dumps({"services": [{"service_id": "climate", "properties": {"room_id": "room1", "ts": 0, "temp_c": 500}}]}).encode(),
        json.dumps({"services": [csi("room2")]}).encode(),  # this device may only report room1
        json.dumps({"services": [csi("room1", ts=now + 7200)]}).encode(),
        json.dumps({"services": [csi("room1", pad="x" * 5000)]}).encode(),  # over 4 KB
    ]
    for payload in bad:
        if len(payload) > 4096:  # the broker cuts the connection for this one (max_packet_size): fire and forget
            c.publish(topic(SIM_DEVICE), payload, qos=0)
        else:
            c.publish(topic(SIM_DEVICE), payload, qos=1).wait_for_publish(5)
    time.sleep(3)
    for _ in range(30):  # paho logs in again by itself
        if c.is_connected():
            break
        time.sleep(0.5)
    check("MQTT bad payloads: nothing stored", rows() == before, rows() - before)
    check("MQTT report for a room the device may not use: refused", rows() == before)
    c.publish(topic(SIM_DEVICE), json.dumps({"services": [csi("room1", ts=now - 2)]}), qos=1).wait_for_publish(5)
    time.sleep(2)
    check("MQTT valid report after the bad ones is stored", rows() == before + 1, rows() - before)
    before = rows()
    c.publish(topic("nadi-recv-1"), json.dumps({"services": [csi("room1", ts=now - 1)]}), qos=1).wait_for_publish(5)
    time.sleep(2)
    check("MQTT publish on another device's topic: dropped by the broker", rows() == before, rows() - before)
    c.loop_stop()
    c.disconnect()

    anon = mqtt_client(None, client_id="anon-test")
    check("MQTT without login: refused", anon.rc is not None and anon.rc.is_failure, anon.rc)
    anon.loop_stop()
    wrong = mqtt_client(SIM_DEVICE, password="wrong-password", client_id="wrong-pass-test")
    check("MQTT wrong password: refused", wrong.rc is not None and wrong.rc.is_failure, wrong.rc)
    wrong.loop_stop()


def abuse(url):
    chat = url + "/api/chat"
    ip = {"X-Forwarded-For": "10.66.0.1"}
    for i in range(5):
        request("POST", chat, {"question": "hi"}, {**ip, "X-Admin-Token": f"guess-{i}"})
    s, r = request("POST", chat, {"question": "hi"}, {**ip, "X-Admin-Token": "guess-again"})
    check("brute force: 5 wrong tokens lock the IP, further guesses get 429", s == 429, (s, r))
    s, _ = request("POST", chat, {"question": "hi"}, {**ip, **HEADERS})
    check("brute force: a warden on the same IP is not locked out (right token works)", s == 200, s)

    # limits use fixed one-minute windows: start just after one opens, and ask something no rule answers so no reply
    # waits for the chat model (with Ollama running, 15 rephrased answers can take longer than the window)
    time.sleep((60 - time.time() % 60) + 0.5 if time.time() % 60 > 40 else 0)
    codes = [request("POST", chat, {"question": "hi"}, {"X-Forwarded-For": "10.66.0.2", **HEADERS})[0]
             for _ in range(15)]
    check("chat flood: 10 per minute per IP, then 429", codes[:10] == [200] * 10 and set(codes[10:]) == {429}, codes)

    em = url + "/api/emergency"
    codes = [request("POST", em, {"on": i % 2 == 0}, {"X-Forwarded-For": "10.66.0.3", **HEADERS})[0] for i in range(10)]
    check("emergency toggle spam: 6 per minute per IP, then 429", codes[:6] == [200] * 6 and set(codes[6:]) == {429}, codes)
    request("POST", em, {"on": False}, {"X-Forwarded-For": "10.66.0.4", **HEADERS})

    from server import store

    def new_actions(since):
        # by time, not by list length: once the log holds AUDIT_KEEP entries its length stops growing
        return [e["action"] for e in store.audit_log() if e.get("ts", 0) >= since and e.get("by") == "stress"]

    def together(n, fn):
        barrier, out = threading.Barrier(n), []

        def run(i):
            barrier.wait()
            out.append(fn(i))
        ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        return out

    time.sleep(1.1)  # the toggle-spam alerts above must fall in an earlier second
    press_ts = int(time.time())
    starts = together(10, lambda i: request("POST", em, {"on": True}, {"X-Forwarded-For": f"10.66.2.{i}", **HEADERS}))
    sinces = {r.get("since") for s, r in starts if s == 200}
    check("two wardens at once: one alarm time", len(sinces) == 1 and all(s == 200 for s, _ in starts), sinces)
    log = store.audit_log()
    check("two wardens at once: one start in the audit log", new_actions(press_ts) == ["start"], log[:3])
    _, rooms = request("GET", url + "/api/rooms")
    audit_alerts = [a for a in rooms["alerts"] if a["subject"] == "NADI: Emergency mode started by stress"
                    and a["ts"] >= press_ts]
    check("audit shown in alerts (who and time, no IP), once for the simultaneous presses",
          len(audit_alerts) == 1 and re.fullmatch(r"stress at \d\d:\d\d:\d\d\.", audit_alerts[0]["message"]), audit_alerts)
    s, a = request("GET", url + "/api/audit", headers={"X-Forwarded-For": "10.66.4.1"})
    check("audit log with IP needs the admin token", s == 401, s)
    s, a = request("GET", url + "/api/audit", headers={"X-Forwarded-For": "10.66.4.1", **HEADERS})
    check("audit log with the token has the IP", s == 200 and a["audit"][0]["ip"].startswith("10.66.2."), a)
    ends = together(10, lambda i: request("POST", em, {"on": False}, {"X-Forwarded-For": f"10.66.3.{i}", **HEADERS}))
    log = store.audit_log()
    check("ending at once: one end in the audit log, all see it off",
          new_actions(press_ts) == ["end", "start"] and all(r.get("on") is False and r.get("since") is None for _, r in ends),
          log[:3])


def security_pass(url):
    """The attacks added with the security pass, against the same server."""
    em = url + "/api/emergency"
    s, r = request("POST", em, {"on": True}, {"X-Forwarded-For": "127.0.0.1"})
    check("X-Forwarded-For: 127.0.0.1 is not 'this computer': no admin", s == 401, (s, r))
    s, r = request("POST", em, {"on": True}, {"X-Real-IP": "127.0.0.1", "Forwarded": "for=127.0.0.1"})
    check("X-Real-IP / Forwarded headers also cancel localhost admin", s == 401, (s, r))

    me = [request("GET", url + "/api/me", headers={"X-Forwarded-For": "10.66.7.1", "X-Admin-Token": f"guess-me-{i}"})[1]
          for i in range(6)]
    check("guessing tokens through /api/me: counted, 429 after 5", [m.get("status") for m in me] == [401] * 5 + [429],
          [m.get("status") for m in me])

    codes, retry = [], None
    for _ in range(260):
        req = __import__("urllib.request").request.Request(url + "/api/rooms", headers={"X-Forwarded-For": "10.66.5.1"})
        try:
            with __import__("urllib.request").request.urlopen(req, timeout=10) as resp:
                codes.append(resp.status)
        except __import__("urllib.error").error.HTTPError as e:
            codes.append(e.code)
            retry = retry or e.headers.get("Retry-After")
    check("read flood from one IP: 429 after 240 a minute, with Retry-After",
          codes.count(200) == 240 and set(codes[240:]) == {429} and retry and int(retry) >= 1, (codes.count(200), retry))
    s, _ = request("GET", url + "/api/rooms", headers={"X-Forwarded-For": "10.66.5.2"})
    check("read flood: other IPs still served", s == 200, s)

    import urllib.request
    with urllib.request.urlopen(url + "/", timeout=10) as resp:
        h = resp.headers
    check("security headers on the console page",
          "script-src 'self'" in h.get("Content-Security-Policy", "") and h.get("X-Frame-Options") == "DENY"
          and h.get("X-Content-Type-Options") == "nosniff" and h.get("Referrer-Policy") == "no-referrer", dict(h))

    iotda = url + "/iotda" + (f"?token={os.environ['INGEST_TOKEN']}" if os.getenv("INGEST_TOKEN") else "")
    now = int(time.time())
    before = mysql_count("room_id = 'room2' AND ts >= %s", (now - 60,))
    outs = [request("POST", iotda, envelope([csi("room2", ts=now - 30 + i)]))[1] for i in range(5)]
    after = mysql_count("room_id = 'room2' AND ts >= %s", (now - 60,))
    check("board flooding reports: only one per half interval stored, the rest dropped",
          after - before == 1 and sum(o.get("dropped", 0) for o in outs) == 4, (after - before, outs))

    from server import store
    store.r.delete("suspicious_alert:room3", "pending_count:room3")  # at most one such alert per room per hour
    store.r.hdel("room:room3", "headcount", "count_ts", "at_least")  # no count left over from an earlier run

    def count(n, ts):
        return request("POST", iotda, envelope([{"service_id": "count", "properties": {"room_id": "room3", "ts": ts, "headcount": n}}]))[1]
    a = count(5, int(time.time()) - 25)
    time.sleep(10.5)
    b = count(95, int(time.time()) - 15)
    _, rooms = request("GET", url + "/api/rooms")
    shown = next((x["headcount"] for x in rooms["rooms"] if x["room_id"] == "room3"), None)
    check("forged jump in a count (5 to 95): held back, not shown", a.get("saved") == 1 and b.get("suspicious") == 1 and shown == 5,
          (a, b, shown))
    sus = [x for x in rooms["alerts"] if x["subject"].endswith("Suspicious reading")]
    check("forged jump: a 'suspicious reading' alert", len(sus) == 1, [x["subject"] for x in rooms["alerts"][:3]])
    time.sleep(10.5)
    c = count(96, int(time.time()) - 5)
    check("a real jump is accepted when the next report agrees", c.get("saved") == 1, c)

    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 2))
    big = mqtt_client(SIM_DEVICE, client_id="oversize-test")
    big.publish(topic(SIM_DEVICE), b"x" * 5000, qos=0)
    time.sleep(2)
    big.loop_stop()
    logs = subprocess.run(["docker", "compose", "logs", "--since", since, "mosquitto"], cwd=ROOT, capture_output=True,
                          text=True).stdout
    check("MQTT packet over 4 KB: broker disconnects the client", "oversize packet" in logs, logs[-300:])

    socks = []
    try:
        for _ in range(60):
            s = socket.create_connection(("127.0.0.1", 1883), timeout=3)
            socks.append(s)
        time.sleep(1)
        extra = mqtt_client(SIM_DEVICE, client_id="conn-limit-test")
        refused = extra.rc is None or extra.rc.is_failure
        extra.loop_stop()
    finally:
        for s in socks:
            s.close()
    time.sleep(2)
    again = mqtt_client(SIM_DEVICE, client_id="conn-limit-after")
    check("broker connection flood: new connections refused at the limit, fine again after",
          refused and again.rc is not None and not again.rc.is_failure, (refused, again.rc))
    again.loop_stop()


def incident_pass(url):
    """The fixes and features of the incident and security pass, against the same server."""
    em = url + "/api/emergency"
    s, r = request("POST", url + "/api/devices/clear", {}, {"Origin": "http://evil.example"})
    check("CSRF: a POST from another website is refused (403)", s == 403, (s, r))
    s, r = request("POST", em, {"on": True}, {"Origin": "http://127.0.0.1:%d" % PORT, "Sec-Fetch-Site": "cross-site"})
    check("CSRF: Sec-Fetch-Site cross-site is refused even with a matching Origin", s == 403, (s, r))
    s, r = request("POST", em, {"on": True}, {"Host": "attacker.example:%d" % PORT})
    check("DNS rebinding: a foreign Host name is not 'this computer' (no admin)", s in (401, 403), (s, r))
    s, _ = request("GET", url + "/api/me", headers={"Host": "attacker.example"})
    check("DNS rebinding: /api/me says not admin", _.get("admin") is False, _)

    if not os.getenv("INGEST_TOKEN"):
        s, r = request("POST", url + "/iotda", envelope([csi("room1", ts=int(time.time()) - 3)]), {"X-Forwarded-For": "10.66.8.1"})
        check("/iotda without INGEST_TOKEN: refused from another address (401)", s == 401, (s, r))
    else:
        check("/iotda without INGEST_TOKEN: skipped (INGEST_TOKEN is set in .env)", True)
    for path in ("/docs", "/redoc", "/openapi.json"):
        s, _ = request("GET", url + path, headers={"X-Forwarded-For": "10.66.8.2"})
        check(f"API docs {path}: refused to a caller that is not admin", s in (401, 403), s)
    s, spec = request("GET", url + "/openapi.json", headers=HEADERS)
    check("API docs: admin token gets the schema", s == 200 and "/api/emergency" in spec.get("paths", {}), s)

    ip = {"X-Forwarded-For": "10.66.8.3"}
    s, r = request("POST", em, {"on": True, "drill": True}, {**ip, **HEADERS})
    check("drill: started", s == 200 and r.get("drill") is True and "-drill-" in (r.get("id") or ""), r)
    _, rooms = request("GET", url + "/api/rooms")
    drill_alerts = [a for a in rooms["alerts"] if a["subject"].startswith("[DRILL]")]
    check("drill: its alerts say [DRILL] and are never critical", len(drill_alerts) >= 2
          and all(a["severity"] != "critical" for a in drill_alerts), [a["subject"] for a in rooms["alerts"][:3]])
    s, _ = request("POST", url + "/api/emergency/rooms/room1", {"status": "clear"}, ip)
    check("warden mark without the admin token: 401", s == 401, s)
    s, r = request("POST", url + "/api/emergency/rooms/room1", {"status": "clear"}, {**ip, **HEADERS})
    check("warden mark with the token: stored and shown", s == 200 and r["accountability"]["room1"]["by"] == "stress", r)
    s, r = request("POST", url + "/api/emergency/rooms/room1", {"status": "<script>"}, {**ip, **HEADERS})
    check("warden mark: an unknown status is refused (422)", s == 422, s)
    s, r = request("POST", url + "/api/data/delete", {"confirm": "DELETE ALL DATA"}, ip)
    check("delete all data without the admin token: 401", s == 401, s)
    s, r = request("POST", url + "/api/data/delete", {"confirm": "delete"}, {**ip, **HEADERS})
    check("delete all data without the typed phrase: 422, nothing deleted", s == 422, s)
    s, r = request("POST", url + "/api/data/delete", {"confirm": "DELETE ALL DATA"}, {**ip, **HEADERS})
    check("delete all data during a drill: refused (409)", s == 409, s)
    s, r = request("POST", em, {"on": False}, {**ip, **HEADERS})
    _, rooms = request("GET", url + "/api/rooms")
    check("drill ended: marks reset", s == 200 and rooms["accountability"] == {}, rooms.get("accountability"))
    _, inc = request("GET", url + "/api/incidents")
    last = inc["incidents"][0] if inc.get("incidents") else {}
    check("drill ended: a drill report is listed with the mark counted", last.get("kind") == "drill" and last.get("marked") == 1, last)
    s, _ = request("GET", url + "/api/incidents/..%2F..%2F.env")
    check("report ids cannot reach other files", s == 404, s)


IOTDA_VARIANTS = ("/iotda", "/iotda/", "//iotda", "/IOTDA", "/Iotda/")


def iotda_pass(url):
    """Someone tries to make a room look empty during an emergency, by every way in that does not hold the token."""
    from server import store

    ingest = os.getenv("INGEST_TOKEN", "")
    q = f"?token={ingest}" if ingest else ""
    lan = {"X-Forwarded-For": "10.66.10.1"}
    em = url + "/api/emergency"
    s, _ = request("POST", em, {"on": True}, {**lan, **HEADERS})
    store.r.delete("suspicious_alert:room3", "pending_count:room3")
    store.r.hdel("room:room3", "headcount", "count_ts", "at_least")
    time.sleep(10.5)  # one report per half interval per board and room (the jump test above used room3)

    def zero(n=0, ts=None):
        return envelope([{"service_id": "count", "properties": {"room_id": "room3", "ts": ts or int(time.time()) - 3,
                                                                "headcount": n}}])

    def shown():
        _, rooms = request("GET", url + "/api/rooms")
        return next((x["headcount"] for x in rooms["rooms"] if x["room_id"] == "room3"), None), rooms["emergency"]["on"]

    s2, r = request("POST", url + "/iotda" + q, zero(40, int(time.time()) - 15))
    time.sleep(1.2)  # /api/rooms is cached for 1 s
    check("emergency on and Hall A reports 40 people", s == 200 and s2 == 200 and shown() == (40, True), (s, s2, r, shown()))

    s, _ = request("POST", url + "/iotda", zero(), lan)
    check("fake 0 during an emergency: no token, from the network: 401", s == 401, s)
    s, _ = request("POST", url + "/iotda?token=wrong-0123456789abcdef", zero(), lan)
    check("fake 0 during an emergency: wrong token: 401", s == 401, s)
    codes = [request("POST", url + path + q, zero(), {"Origin": "http://evil.example"})[0] for path in IOTDA_VARIANTS]
    check("fake 0 during an emergency: cross-site POST to /iotda, /iotda/, //iotda, /IOTDA, /Iotda/ (even with the token): 403",
          codes == [403] * len(IOTDA_VARIANTS), codes)
    codes = [request("POST", url + path + q, zero(), {"Sec-Fetch-Site": "cross-site"})[0] for path in IOTDA_VARIANTS]
    check("fake 0 during an emergency: Sec-Fetch-Site cross-site on every /iotda spelling: 403",
          codes == [403] * len(IOTDA_VARIANTS), codes)
    codes = [request("POST", url + path + q, zero())[0] for path in IOTDA_VARIANTS[1:]]
    check("other spellings of /iotda never reach the endpoint or redirect to it (405)", codes == [405] * 4, codes)
    c = mqtt_client(SIM_DEVICE, client_id="fake-zero-test")
    c.publish(topic(SIM_DEVICE), json.dumps(zero()["notify_data"]["body"]), qos=1).wait_for_publish(5)
    time.sleep(2)
    c.loop_stop()
    c.disconnect()
    check("fake 0 during an emergency: over MQTT from a board not allowed in that room: not shown", shown() == (40, True), shown())
    time.sleep(10.5)
    s, r = request("POST", url + "/iotda" + q, zero())
    check("fake 0 during an emergency: 40 to 0 in one report, even with the token: held back, still 40",
          s == 200 and r.get("suspicious") == 1 and shown() == (40, True), (s, r, shown()))
    request("POST", em, {"on": False}, {**lan, **HEADERS})


def empty_ingest_token_server():
    """INGEST_TOKEN empty: only this computer, by its own name and with no proxy header, may post to /iotda."""
    srv = Server(port=PORT + 4, name="attack-noingest", INGEST_TOKEN="").start()
    try:
        ignored = {"resource": "device.message"}  # answered, never stored
        s1, _ = request("POST", srv.url + "/iotda", ignored, {"X-Forwarded-For": "10.66.11.1"})
        s2, _ = request("POST", srv.url + "/iotda?token=anything-0123456789", ignored, {"X-Forwarded-For": "10.66.11.1"})
        s3, _ = request("POST", srv.url + "/iotda", ignored, {"Host": "attacker.example"})
        check("empty INGEST_TOKEN: another address 401, any token 401, a foreign Host name 401", (s1, s2, s3) == (401, 401, 401),
              (s1, s2, s3))
        codes = [request("POST", srv.url + p, ignored, {"Origin": "http://evil.example"})[0] for p in IOTDA_VARIANTS]
        check("empty INGEST_TOKEN: cross-site POST from a browser on this computer, every spelling: 403",
              codes == [403] * len(IOTDA_VARIANTS), codes)
        s, r = request("POST", srv.url + "/iotda", ignored)
        check("empty INGEST_TOKEN: this computer itself (the simulator) still accepted", s == 200 and r.get("ok"), (s, r))
    finally:
        srv.stop()


def viewer_token_server():
    viewer = "viewer-" + os.urandom(12).hex()
    srv = Server(port=PORT + 2, name="attack-viewer", VIEWER_TOKEN=viewer).start()
    try:
        ip = {"X-Forwarded-For": "10.66.6.1"}
        s1, _ = request("GET", srv.url + "/api/rooms", headers=ip)
        s2, _ = request("GET", srv.url + "/api/rooms", headers={**ip, "X-Viewer-Token": viewer})
        s3, _ = request("POST", srv.url + "/api/emergency", {"on": True}, {**ip, "X-Admin-Token": viewer})
        check("viewer token: no token 401, viewer token 200, and it is not an admin token", (s1, s2, s3) == (401, 200, 401),
              (s1, s2, s3))
    finally:
        srv.stop()


def huawei_refuses_defaults():
    env = dict(os.environ, NADI_MODE="huawei", MYSQL_PASSWORD="nadi_local_pw", ADMIN_TOKEN="", ADMIN_TOKENS="", VIEWER_TOKEN="")
    p = subprocess.run([PY, "-m", "uvicorn", "server.main:app", "--port", str(PORT + 3)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    check("huawei mode with default secrets: refuses to start, values not printed",
          p.returncode != 0 and "Refusing to start in huawei mode" in out and "nadi_local_pw" not in out, out[-300:])


def dashboard_escapes(url):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(url + "/floor")
        page.wait_for_timeout(2500)
        fired = page.evaluate("window.__xss === 1")
        shown = min(1, page.locator("svg text", has_text=XSS_NAME).count())
        imgs = page.locator("img").count()
        browser.close()
    check("dashboard: room name with HTML is shown as text, never run", not fired and shown == 1 and imgs == 0,
          {"script_ran": fired, "shown_as_text": shown, "img_elements": imgs})


def main():
    global T0
    from server import store

    T0 = int(time.time()) - 60
    alerts_before = store.r.lrange("alerts", 0, -1)
    for pattern in ("lock:10.66.*", "fail:10.66.*", "rl:*:10.66.*"):  # lockouts and limits left by an earlier run
        for key in store.r.scan_iter(pattern):
            store.r.delete(key)
    server = Server(port=PORT, name="attack-server", DEVICE_ROOMS=f"{SIM_DEVICE}:room1,sim-local:room1,sim-local:room2,sim-local:room3",
                    ROOM_NAMES=f"room1:Lab 2,room2:{XSS_NAME},room3:Hall A")
    log_path = LOGS / "attack-server.log"
    log_start = len(log_path.read_text(encoding="utf-8")) if log_path.exists() else 0
    server.start()
    url = server.url
    try:
        http_bad_input(url)
        mqtt_input()
        abuse(url)
        security_pass(url)
        incident_pass(url)
        iotda_pass(url)
        empty_ingest_token_server()
        dashboard_escapes(url)
        viewer_token_server()
        huawei_refuses_defaults()
        check("server still running after every attack", server.alive())
        log = open(server.log.name, encoding="utf-8").read()[log_start:]
        # Python's asyncio on Windows logs a traceback when a client resets a finished connection
        # (_ProactorBasePipeTransport._call_connection_lost, WinError 10054). That is the read flood's clients
        # hanging up, not a server error, so those blocks are left out.
        rest = re.sub(r"Exception in callback _ProactorBasePipeTransport\._call_connection_lost\(\)\nhandle: [^\n]*\n"
                      r"Traceback \(most recent call last\):\n(?:  [^\n]*\n)*ConnectionResetError: \[WinError 10054\][^\n]*\n",
                      "", log)
        check("no 500 / traceback in the server log (Windows connection-reset noise excluded)",
              "Traceback" not in rest and " 500 " not in rest, rest[rest.find("Traceback"):][:300])
    finally:
        request("POST", url + "/api/emergency", {"on": False}, {"X-Forwarded-For": "10.66.9.9", "X-Admin-Token": TOKEN})
        server.stop()
        pipe = store.r.pipeline()
        pipe.delete("alerts")
        if alerts_before:
            pipe.rpush("alerts", *alerts_before)
        pipe.execute()
    passed = sum(r["pass"] for r in results)
    save("attack", {"passed": passed, "total": len(results), "results": results})
    print(f"ATTACK {passed}/{len(results)} passed", "PASS" if passed == len(results) else "FAIL")


if __name__ == "__main__":
    main()
