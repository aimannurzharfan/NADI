"""Load test: 100 dashboard viewers, 20 chat users and 30 fake boards at once, for 5 minutes.

- Viewers poll GET /api/rooms every 5 s like the dashboard (plus /api/history every 30 s, /api/info every 60 s).
- Every viewer and chat user has its own IP (X-Forwarded-For from a trusted proxy, TRUSTED_PROXIES=127.0.0.1), like
  real people on their own phones and laptops, so the per-IP limits (240 reads a minute) are not what is measured.
- Chat users each ask a question every 10 s.
- Boards publish one CSI report every 2 s through Mosquitto, each for its own test room (load01..load30).
  They log in as the simulator device (the broker's ACL only lets a device use its own topic), one connection each.
Measures p50/p95/max latency and error rate per endpoint, server memory every 5 s, and how many board reports
reached MySQL. Test rooms are removed afterwards.

    python scripts/stress/load.py [--seconds 300]
Target on this laptop: /api/rooms p95 < 300 ms, zero errors, no memory growth.
"""
import argparse
import asyncio
import json
import random
import statistics
import time

import httpx
import psutil

from common import HEADERS, SIM_DEVICE, Server, cleanup_rooms, mqtt_client, mysql_count, pct, save, topic

PREFIX = "load"
BOARDS = 30
VIEWERS = 100
CHATTERS = 20
QUESTIONS = ["How many people are inside?", "Which rooms are empty?", "Berapa orang di dalam?",
             "Bilik mana yang kosong?", "Is the air conditioning on in an empty room?", "Which room should rescuers check first?"]


class Stats:
    def __init__(self):
        self.lat, self.codes, self.errors = {}, {}, {}
        self.retried = 0

    def add(self, name, ms, code):
        self.lat.setdefault(name, []).append(ms)
        self.codes.setdefault(name, {}).setdefault(str(code), 0)
        self.codes[name][str(code)] += 1

    def summary(self):
        out = {}
        for name, lat in self.lat.items():
            codes = self.codes[name]
            bad = sum(n for c, n in codes.items() if not c.startswith("2"))
            out[name] = {"requests": len(lat), "p50_ms": round(pct(lat, 50), 1), "p95_ms": round(pct(lat, 95), 1),
                         "max_ms": round(max(lat), 1), "errors": bad, "error_rate": round(bad / len(lat), 4),
                         "codes": codes}
        return out


async def timed(stats, name, coro, again=None):
    """again: a function that makes the same GET again. The server closes idle keep-alive connections after 5 s
    (--timeout-keep-alive 5) and the dashboard polls every 5 s, so now and then a request goes out on a socket the
    server is just closing. Browsers repeat a GET then; so does this test, once, and counts how often it did."""
    start = time.perf_counter()
    try:
        res = await coro
        code = res.status_code
    except (httpx.RemoteProtocolError, httpx.ReadError) as e:
        code = type(e).__name__
        if again is not None:
            stats.retried += 1
            try:
                code = (await again()).status_code
            except Exception as e2:
                code = type(e2).__name__
    except Exception as e:
        code = type(e).__name__
    stats.add(name, (time.perf_counter() - start) * 1000, code)


async def viewer(client, stats, until, i):
    await asyncio.sleep(random.uniform(0, 5))  # dashboards are not opened at the same instant
    h = {"X-Forwarded-For": f"10.30.{i // 250}.{i % 250 + 1}"}
    n = 0
    while time.time() < until:
        await timed(stats, "GET /api/rooms", client.get("/api/rooms", headers=h), lambda: client.get("/api/rooms", headers=h))
        if n % 6 == 0:
            await timed(stats, "GET /api/history", client.get("/api/history?minutes=30", headers=h),
                        lambda: client.get("/api/history?minutes=30", headers=h))
        if n % 12 == 0:
            await timed(stats, "GET /api/info", client.get("/api/info", headers=h), lambda: client.get("/api/info", headers=h))
        n += 1
        await asyncio.sleep(5)


async def chatter(client, stats, until, i):
    await asyncio.sleep(random.uniform(0, 10))
    headers = {**HEADERS, "X-Forwarded-For": f"10.20.0.{i + 1}"}
    while time.time() < until:
        await timed(stats, "POST /api/chat", client.post("/api/chat", json={"question": random.choice(QUESTIONS)},
                                                          headers=headers))
        await asyncio.sleep(10)


def boards(until, sent):
    clients = []
    for i in range(BOARDS):
        c = mqtt_client(SIM_DEVICE, client_id=f"{SIM_DEVICE}-load{i + 1:02d}")
        if c.rc is None or c.rc.is_failure:
            raise SystemExit(f"board {i + 1}: MQTT login failed ({c.rc}). Is Mosquitto running?")
        clients.append(c)
    t = topic(SIM_DEVICE)
    next_at = time.time()
    while time.time() < until:
        ts = int(time.time())
        for i, c in enumerate(clients):
            body = {"services": [{"service_id": "csi", "properties": {
                "room_id": f"{PREFIX}{i + 1:02d}", "ts": ts, "motion_mean": round(random.uniform(0, 0.3), 4),
                "motion_std": round(random.uniform(0, 1.8), 4), "amp_var": 0.01, "rssi_mean": -55.0, "n_packets": 100}}]}
            c.publish(t, json.dumps(body), qos=1)
            sent.append(ts)
        next_at += 2
        time.sleep(max(0, next_at - time.time()))
    time.sleep(3)
    for c in clients:
        c.loop_stop()
        c.disconnect()


def memory(server, until, samples):
    start = time.time()
    while time.time() < until:
        samples.append([round(time.time() - start), server_mb(server)])
        time.sleep(5)


def server_mb(server):
    """RSS of the server and its children (on Windows the venv python.exe is a launcher for the real one)."""
    proc = psutil.Process(server.proc.pid)
    procs = [proc, *proc.children(recursive=True)]
    return round(sum(p.memory_info().rss for p in procs) / 2**20, 1)


async def run(seconds, port):
    names = ",".join(f"{PREFIX}{i + 1:02d}:Load {i + 1:02d}" for i in range(BOARDS))
    # boards report every 2 s; with the chat model busy, reports reach the server bunched up (seen: 1.5 and 1 s
    # limits each dropped some), so the per-device limit is 0.5 s here. This measures throughput, not the flood check
    # (attack.py tests that); real boards report every 20 s against a 10 s limit
    server = Server(port=port, name="load-server", ROOM_NAMES=names, DEVICE_ROOMS=f"{SIM_DEVICE}:*",
                    REPORT_INTERVAL_S=3, DEVICE_MIN_GAP_S=0.5).start()
    cleanup_rooms(PREFIX)
    stats, sent, mem = Stats(), [], []
    t0 = int(time.time())
    until = time.time() + seconds
    print(f"load: {VIEWERS} viewers, {CHATTERS} chat users, {BOARDS} boards every 2 s, for {seconds} s")
    try:
        # idle sockets are dropped after 4 s, before the server's 5 s (--timeout-keep-alive 5), as a client should
        limits = httpx.Limits(max_connections=VIEWERS + CHATTERS + 10, max_keepalive_connections=VIEWERS + CHATTERS,
                              keepalive_expiry=4.0)
        async with httpx.AsyncClient(base_url=server.url, timeout=15, limits=limits) as client:
            loop = asyncio.get_running_loop()
            board_job = loop.run_in_executor(None, boards, until, sent)
            mem_job = loop.run_in_executor(None, memory, server, until, mem)
            await asyncio.gather(*[viewer(client, stats, until, i) for i in range(VIEWERS)],
                                 *[chatter(client, stats, until, i) for i in range(CHATTERS)])
            await board_job
            await mem_job
        time.sleep(3)  # let the last reports land
        stored = mysql_count("room_id LIKE %s AND ts >= %s", (PREFIX + "%", t0))
        alive = server.alive()
    finally:
        server.stop()
        cleanup_rooms(PREFIX)

    summary = stats.summary()
    warm = [m for t, m in mem if 30 <= t <= 90]
    late = [m for t, m in mem if t >= seconds - 60]
    growth = round(statistics.median(late) - statistics.median(warm), 1) if warm and late else None
    result = {"seconds": seconds, "viewers": VIEWERS, "chat_users": CHATTERS, "boards": BOARDS,
              "endpoints": summary, "board_reports_sent": len(sent), "board_reports_stored": stored,
              "board_reports_lost": len(sent) - stored, "get_retries_after_keepalive_close": stats.retried,
              "memory_mb": {"start": mem[0][1] if mem else None, "after_warmup_median": statistics.median(warm) if warm else None,
                            "last_minute_median": statistics.median(late) if late else None, "growth": growth,
                            "max": max(m for _, m in mem) if mem else None, "samples": mem},
              "server_alive": alive}
    rooms = summary.get("GET /api/rooms", {})
    errors = sum(s["errors"] for s in summary.values())
    checks = {
        "rooms_p95_under_300ms": rooms.get("p95_ms", 1e9) < 300,
        "zero_errors": errors == 0,
        "no_lost_reports": result["board_reports_lost"] == 0,
        "no_memory_growth": growth is not None and growth < 20,  # MB between minute 1 and the last minute
        "server_alive": alive,
    }
    result["checks"] = checks
    result["pass"] = all(checks.values())
    save("load", result)
    for name, s in summary.items():
        print(f"{name:20s} n={s['requests']:5d}  p50={s['p50_ms']:7.1f} ms  p95={s['p95_ms']:7.1f} ms  "
              f"max={s['max_ms']:7.1f} ms  errors={s['errors']} {s['codes']}")
    print(f"boards: sent {len(sent)}, stored {stored}, lost {result['board_reports_lost']}")
    print(f"GETs repeated once after the server closed an idle keep-alive connection: {stats.retried}")
    print(f"server memory MB: start {result['memory_mb']['start']}, after warm-up {result['memory_mb']['after_warmup_median']}, "
          f"last minute {result['memory_mb']['last_minute_median']}, growth {growth}")
    for k, v in checks.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print("LOAD", "PASS" if result["pass"] else "FAIL")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    asyncio.run(run(a.seconds, a.port))
