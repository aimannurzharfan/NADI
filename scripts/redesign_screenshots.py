"""Screenshots of the console in fixed states, from sample data (never real sensor data).

No NADI server, Redis, MySQL or board is used: the built console (web/dist) is served from a throw-away local web
server and every /api/ call the page makes is answered by this script. The building is named
"Demo building (sample data)" so no screenshot can pass for a real reading.

    python scripts/redesign_screenshots.py                 # every screenshot in SHOTS (1920x1080 unless named)
    python scripts/redesign_screenshots.py --only overview-all-clear,energy
    python scripts/redesign_screenshots.py --video         # only tile-calm-active-calm.webm (about 55 s, not committed)
    python scripts/redesign_screenshots.py --frames DIR    # only close-up PNG frames of the room tile
    python scripts/redesign_screenshots.py --cpu 600       # leave the page open for 600 s and report CPU use
    python scripts/redesign_screenshots.py --out DIR       # save to DIR instead of docs/screenshots/redesign

Output: docs/screenshots/redesign/, PNG with image chunks only (no text or metadata chunks). Uses Microsoft Edge if
installed, otherwise Playwright's Chromium.
"""
import argparse
import functools
import http.server
import json
import math
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
OUT = ROOT / "docs" / "screenshots" / "redesign"
STRINGS = json.loads((ROOT / "dashboard" / "strings.json").read_text(encoding="utf-8"))
BUILDING = "Demo building (sample data)"
NAMES = {"room1": "Demo Room", "room2": "Hall A", "room3": "Room 3"}
THRESHOLD = 1.301
INTERVAL = 10  # seconds between reports, as on the real boards
MYT = 8 * 3600
NOW_DAY_INDEX = [0]  # the fixture's Malaysian day number, set before past_day_rm reads it
AC_KW, TARIFF, WASTE_MIN = 10, 0.2983, 10  # the server's defaults: AC_KW, TARIFF_RM_PER_KWH, WASTE_MINUTES
EPISODE = (107 * 60, 95 * 60)    # seconds ago: the room stood empty with the air conditioning on from, until
OUTAGE = (47 * 60 + 30, 46 * 60)  # seconds ago: the sensor's last report before it went quiet, its first one after
LABELLED_OCCUPIED = (60 * 60, 58 * 60)  # seconds ago: the room was labelled "1 person" from, until (and it was)
SENSOR_OFF_DAYS = (3, 4)  # days ago: the sensor was switched off, so those days are a gap in every chart
CAPACITY = 2  # the Demo Room's capacity on the sample plan: the dashed line of the people chart
PATTERN = [0, 0, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1]  # occupied or not, per quarter of an hour, for the older history


def t(key, lang="en", **values):
    text = STRINGS[key][lang]
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


class Console(http.server.SimpleHTTPRequestHandler):
    """web/dist with the single-page fallback: any path that is not a file gets index.html."""

    def translate_path(self, path):
        found = Path(super().translate_path(path))
        return str(found if found.is_file() else DIST / "index.html")

    def log_message(self, format, *args):
        pass


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128  # the browser opens a connection per file: none may be refused


def serve():
    server = Server(("127.0.0.1", 0), functools.partial(Console, directory=str(DIST)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def noise(ts):
    """A steady room: about 0.25 to 0.75 dB, the same for the same second every run."""
    return 0.5 + 0.25 * math.sin(ts * 0.731) * math.cos(ts * 0.173)


def movement(ts):
    """Someone crossing the line between the boards: about 1.8 to 3.2 dB."""
    return 2.5 + 0.7 * math.sin(ts * 0.911)


def rm(seconds):
    """What the air conditioning costs over this long, as the server works it out."""
    return round(AC_KW * TARIFF * seconds / 3600, 2)


class Fixture:
    """The API answers for one state. `state`: calm, occupied, waste, offline, emergency or video.

    Every answer is read off ONE made-up day for room1, so the screens agree with each other (times before now):

        6 h          the sensor's first report today (or midnight, if that is later); one report every 10 s
        107 to 95 min  the room stood empty with the air conditioning on: an alert at the 10-minute mark (97 min ago,
                     "10 minutes, RM0.50"), RM0.60 by the time someone came back, which is today's waste total
        47.5 to 46 min the sensor missed its reports: "not reported for 30 seconds" 47 min ago, "reporting again"
                     46 min ago, and the uptime figure is below 100% by those 90 seconds
        waste state  empty for the last 10 min 5 s: the card says 10 min and RM0.50, the alert raised 5 s ago says the
                     same, and today's total is RM0.60 + RM0.50
        offline state  the last report came 140 s before the page opened (someone was inside), the alert followed
                     30 s later, and the signal chart, the history and the uptime all stop there
    The threshold rule tells empty from occupied only, so no count is ever above 1.
    """

    def __init__(self, state, lang="en", many=False, viewer=False, db_down=False):
        """many: thirteen labels and fourteen more alerts, to show the list rule; viewer: not an admin; db_down: the
        history database went offline five minutes ago (the banner)."""
        self.state, self.lang, self.t0, self.many, self.viewer = state, lang, int(time.time()), many, viewer
        self.db_down = db_down

    # --- the made-up day ---

    def first_report(self, now):
        midnight = (now + MYT) // 86400 * 86400 - MYT
        return -(-max(midnight, now - 6 * 3600) // INTERVAL) * INTERVAL

    def last_report(self, now):
        if self.state == "offline":
            return (self.t0 - 140) // INTERVAL * INTERVAL
        return now - now % INTERVAL

    def sensor_up(self, ts, now):
        """Whether the sensor sent the report due at ts."""
        if not self.first_report(now) <= ts <= self.last_report(now):
            return False
        return not now - OUTAGE[0] < ts < now - OUTAGE[1]

    def waste_since(self, now):
        return now - (WASTE_MIN * 60 + 5) if self.state == "waste" else None

    def moving(self, ts, now):
        """Whether someone is crossing the signal line at ts (the last few minutes, as the signal chart draws them)."""
        if self.state == "video":  # calm, then movement from 15 s to 35 s after the page opened, then calm again
            return 15 <= ts - self.t0 < 35
        ago = now - ts
        if self.state in ("occupied", "emergency"):
            return ago < 60 or 170 <= ago < 200
        if self.state == "offline":  # someone was inside when the sensor stopped
            return self.last_report(now) - 40 <= ts
        if self.state == "waste":
            return False
        return 200 <= ago < 230  # someone left a few minutes ago

    def count_at(self, ts, now):
        """0 or 1: what the sensor said at ts."""
        ago = now - ts
        since = self.waste_since(now)
        if since is not None:
            if ts >= since:
                return 0
            if ts >= since - 600:
                return 1  # someone was inside until the room emptied
        if EPISODE[1] < ago <= EPISODE[0]:
            return 0
        if EPISODE[1] - 600 < ago <= EPISODE[0] + 600:
            return 1  # inside just before the room emptied, and back when it ended
        if ago < 300:
            return 1 if self.moving(ts, now) else 0
        if LABELLED_OCCUPIED[1] <= ago <= LABELLED_OCCUPIED[0]:
            return 1  # the second label of the calibration page: someone stood in the room while it was labelled
        return PATTERN[(ts // 900) % len(PATTERN)]

    # --- the API answers ---

    def room1(self, now):
        ts = self.last_report(now)
        live = self.state != "offline"
        since = self.waste_since(now)
        waste = {"since": since, "minutes": (now - since) // 60, "rm": rm(now - since)} if since else None
        return {"room_id": "room1", "name": NAMES["room1"], "headcount": self.count_at(ts, now), "at_least": False,
                "counter": "csi", "count_ts": ts, "temp_c": 23.8 if waste else 24.6, "humidity": 61.0, "live": live, "waste": waste}

    def alert(self, now, ago, icon, severity, subject_key, body_key, **values):
        values = {**values, "minute_word": t("unit.minutes", self.lang)}
        return {"id": f"{now - ago:x}-fixture", "ts": now - ago, "kind": icon, "severity": severity, "via": "console",
                "subject": t(subject_key, self.lang, **values), "message": t(body_key, self.lang, **values), "ack": None, "drill": False}

    def alerts(self, now):
        if self.many:  # a bad morning for the sensor: seven more outages, each with its "back online", all after
            # today's first report (the list rule needs more than ten rows)
            name, kind = NAMES["room1"], t("sensors.type_receiver", self.lang)
            older = []
            for i in range(7):
                back = 3 * 3600 + i * 20 * 60  # seconds ago
                older.append(self.alert(now, back, "sensor", "info", "alert.sensor_online_subject", "alert.sensor_online_body", rooms=name, kind=kind))
                older.append(self.alert(now, back + 90, "sensor", "warning", "alert.sensor_offline_subject", "alert.sensor_offline_body",
                                        rooms=name, kind=kind, seconds=3 * INTERVAL))
            return self.usual_alerts(now) + older
        return self.usual_alerts(now)

    def usual_alerts(self, now):
        name, kind = NAMES["room1"], t("sensors.type_receiver", self.lang)
        stale = 3 * INTERVAL
        flagged = WASTE_MIN * 60  # an alert goes out when a room has been empty with the air conditioning on this long
        out = [
            self.alert(now, OUTAGE[1], "sensor", "info", "alert.sensor_online_subject", "alert.sensor_online_body", rooms=name, kind=kind),
            self.alert(now, OUTAGE[0] - stale, "sensor", "warning", "alert.sensor_offline_subject", "alert.sensor_offline_body",
                       rooms=name, kind=kind, seconds=stale),
            self.alert(now, EPISODE[0] - flagged, "waste", "warning", "alert.waste_subject", "alert.waste_body", name=name,
                       minutes=WASTE_MIN, temp="24.1", rm=f"{rm(flagged):.2f}"),
        ]
        since = self.waste_since(now)
        if since:
            out.insert(0, self.alert(now, now - since - flagged, "waste", "warning", "alert.waste_subject", "alert.waste_body", name=name,
                                     minutes=WASTE_MIN, temp="23.8", rm=f"{rm(flagged):.2f}"))
        if self.state == "offline":
            out.insert(0, self.alert(now, now - self.last_report(now) - stale, "sensor", "warning", "alert.sensor_offline_subject",
                                     "alert.sensor_offline_body", rooms=name, kind=kind, seconds=stale))
        if self.state == "emergency":
            # every room is reporting, so the server words it with the plain body (no "unknown" list)
            out.insert(0, self.alert(now, 95, "emergency", "critical", "alert.emergency_subject", "alert.emergency_body",
                                     total=1, rooms=f"{name}: 1"))
        return out

    def rooms(self, now):
        emergency = {"on": self.state == "emergency", "since": now - 95 if self.state == "emergency" else None, "drill": False,
                     "id": "fixture" if self.state == "emergency" else None}
        room = self.room1(now)
        today = rm(EPISODE[0] - EPISODE[1]) + (room["waste"]["rm"] if room["waste"] else 0)
        return {"now": now, "stale_s": 3 * INTERVAL, "rooms": [room], "waste_today_rm": round(today, 2),
                "waste_today_kwh": round(today / TARIFF, 1), "emergency": emergency, "accountability": {}, "alerts": self.alerts(now), "offline": {"mysql": now - 300} if self.db_down else {}, "stale_ts": None,
                "demo": {"on": False, "t": None}, "clock": None}

    def signal(self, now, minutes=5):
        points, ts = [], self.last_report(now)
        while ts > now - minutes * 60:
            if self.sensor_up(ts, now):
                count = self.count_at(ts, now)
                points.append({"ts": ts, "motion_std": round(movement(ts) if count else noise(ts), 4), "headcount": count})
            ts -= INTERVAL
        points.reverse()
        return {"now": now, "room_id": "room1", "minutes": minutes, "threshold": THRESHOLD, "points": points,
                "last_report_ts": points[-1]["ts"] if points else None}

    def reports(self, now, since):
        """The times of the reports the sensor sent from `since` on."""
        start = max(self.first_report(now), -(-since // INTERVAL) * INTERVAL)
        return [ts for ts in range(start, self.last_report(now) + 1, INTERVAL) if self.sensor_up(ts, now)]

    def long_history(self, now, minutes, room):
        """7 or 30 days, as the server answers them: one point an hour (7 days) or a Malaysian day (30 days), the
        highest count in it; office hours busy on weekdays, a two-day sensor gap (no points), and some empty hours
        with the air conditioning on (the "waste" buckets)."""
        bucket = 3600 if minutes <= 7 * 24 * 60 else 86400
        off = MYT if bucket == 86400 else 0
        first = (now - minutes * 60 + off) // bucket * bucket - off
        points, waste = [], []
        for b in range(first, now + 1, bucket):
            day_index = (now - b) // 86400
            if day_index in SENSOR_OFF_DAYS:  # the sensor was off: nothing stored, a gap in the chart
                continue
            weekday = ((b + MYT) // 86400 + 3) % 7 < 5  # 1 Jan 1970 was a Thursday
            hour = (b + MYT) // 3600 % 24
            if bucket == 86400:
                n = 2 if weekday else 0
                cold = not weekday
            else:
                n = (2 if 10 <= hour < 12 or 14 <= hour < 16 else 1) if weekday and 9 <= hour < 18 else 0
                cold = weekday and hour in (18, 19)  # left on after work
            points.append([b, n])
            if n == 0 and cold:
                waste.append(b)
        out = {"now": now, "bucket_s": bucket, "rooms": {"room1": points}}
        if room:
            out["waste"] = waste
        return out

    FIRST_DAYS_AGO = 24  # the first report: 24 days ago, so the 30 days start with six empty days

    @staticmethod
    def past_day_rm(days_ago, room_id):
        """RM wasted on an earlier day: weekday evenings in the Demo Room; Hall A and Room 3 have no sensor, so nothing
        is known about them. None on the two days the sensor was off."""
        weekday = ((NOW_DAY_INDEX[0] - days_ago) + 3) % 7 < 5
        if room_id == "room1" and days_ago not in SENSOR_OFF_DAYS:
            return round((0.6 + 0.3 * ((days_ago * 7) % 5) / 4) if weekday else 0.0, 2)
        return 0.0

    def energy(self, now, rng, room=""):
        """/api/energy: today is the Demo Room's episode and its running stretch (as the room answer says); earlier
        days follow past_day_rm, from the first report on. The totals, rooms, days and hours all agree. With room, the
        hours or days are that room's ("series_room")."""
        NOW_DAY_INDEX[0] = (now + MYT) // 86400
        today = self.rooms(now)["waste_today_rm"]
        rate = AC_KW * TARIFF / 3600

        def amounts(r):
            return {"rm": round(r, 2), "kwh": round(r / TARIFF, 1), "co2_kg": round(r / TARIFF * 0.75, 1)}

        def day_rm(d, room_id=None):
            if d == 0:
                return today if room_id in (None, "room1") else 0.0
            if d > self.FIRST_DAYS_AGO:
                return 0.0
            return sum(self.past_day_rm(d, r) for r in NAMES) if room_id is None else self.past_day_rm(d, room_id)

        n = {"today": 1, "7d": 7, "30d": 30}.get(rng, 7)
        midnight = (now + MYT) // 86400 * 86400 - MYT
        start = midnight - (n - 1) * 86400
        first = midnight - self.FIRST_DAYS_AGO * 86400 + 9 * 3600
        total = sum(day_rm(d) for d in range(n))
        previous = None if first >= start else amounts(sum(day_rm(d) for d in range(n, 2 * n)))
        by_room = []
        for r in NAMES:
            spent = sum(day_rm(d, r) for d in range(n))
            by_room.append({"room_id": r, "name": NAMES[r], "rm": round(spent, 2), "kwh": round(spent / TARIFF, 1),
                            "hours": round(spent / TARIFF / AC_KW, 1)})
        one = room if room in NAMES else None
        if rng == "today":
            hours = [0.0] * 24
            stretches = [(now - EPISODE[0], now - EPISODE[1])]
            since = self.waste_since(now)
            if since and self.room1(now)["waste"]:
                stretches.append((since, now))
            for a, b in stretches if one in (None, "room1") else []:
                while a < b:
                    end = min(b, (a // 3600 + 1) * 3600)
                    if a >= midnight:
                        hours[(a - midnight) // 3600] += (end - a) * rate
                    a = end
            points = [{"ts": midnight + h * 3600, "rm": None if midnight + h * 3600 > now else round(hours[h], 2)} for h in range(24)]
            series = {"unit": "hour", "points": points}
        else:
            series = {"unit": "day", "points": [
                {"day": time.strftime("%Y-%m-%d", time.gmtime(midnight - d * 86400 + MYT)),
                 "rm": None if midnight - d * 86400 + 86400 <= first else round(day_rm(d, one), 2)} for d in range(n - 1, -1, -1)]}
        week = sum(day_rm(d) for d in range(7))
        return {"now": now, "today": amounts(today), "week": amounts(week), "previous_week": amounts(sum(day_rm(d) for d in range(7, 14))),
                "yesterday": amounts(day_rm(1)),
                "by_room": [{"room_id": r, "name": NAMES[r], "rm_today": round(day_rm(0, r), 2),
                             "rm_week": round(sum(day_rm(d, r) for d in range(7)), 2)} for r in NAMES],
                "daily": [{"day": time.strftime("%Y-%m-%d", time.gmtime(midnight - d * 86400 + MYT)), "rm": round(day_rm(d), 2)}
                          for d in range(6, -1, -1)],
                "tariff_rm_per_kwh": TARIFF, "ac_kw": AC_KW, "co2_kg_per_kwh": 0.75, "rate_changes": [], "stale_ts": None,
                "range": {"id": rng if rng in ("today", "7d", "30d") else "7d", "days": n, "total": amounts(total), "previous": previous,
                          "by_room": by_room, "series": series, "series_room": one, "first_ts": first}}

    def history(self, now, minutes, room=""):
        """One point per bucket that has a report: the highest count in it, as the server answers."""
        if minutes > 24 * 60:
            return self.long_history(now, minutes, room)
        bucket = 60 if minutes <= 60 else 900
        midnight = (now + MYT) // 86400 * 86400 - MYT
        peaks = {}
        for ts in self.reports(now, max(midnight, now - minutes * 60)):
            b = ts // bucket * bucket
            peaks[b] = max(peaks.get(b, 0), self.count_at(ts, now))
        return {"now": now, "bucket_s": bucket, "rooms": {"room1": [[b, n] for b, n in sorted(peaks.items())]}}

    def earlier(self, ts, now):
        """0 or 1 for a minute before today's first report, None when the sensor sent nothing: installed 24 days ago
        at 09:00, off for two days, someone inside in office hours on weekdays (not at lunch), off from midnight until
        today's first report."""
        midnight = (now + MYT) // 86400 * 86400 - MYT
        if ts >= midnight or ts < midnight - self.FIRST_DAYS_AGO * 86400 + 9 * 3600:
            return None
        if (midnight - ts - 1) // 86400 + 1 in SENSOR_OFF_DAYS:
            return None
        weekday = ((ts + MYT) // 86400 + 3) % 7 < 5  # 1 Jan 1970 was a Thursday
        hour = (ts + MYT) // 3600 % 24
        return 1 if weekday and 9 <= hour < 18 and hour != 13 else 0

    def people(self, now, minutes):
        """GET /api/history?room=room1&view=people as the server answers: per bucket the highest count and the minutes
        with someone inside, buckets on whole steps of Malaysian time, none where there was no report; and since when
        the room has been empty or occupied without a break."""
        bucket = next((b for most, b in ((60, 60), (1440, 1800), (10080, 10800)) if minutes <= most), 86400)
        off = MYT % bucket
        since, first = now - minutes * 60, self.first_report(now)
        seen = {}

        def note(ts, count):
            at = seen.setdefault((ts + off) // bucket * bucket - off, [0, set()])
            at[0] = max(at[0], count)
            if count:
                at[1].add(ts // 60)

        sent = self.reports(now, max(since, first))
        for ts in sent:
            note(ts, self.count_at(ts, now))
        for ts in range(-(-since // 60) * 60, first, 60):
            count = self.earlier(ts, now)
            if count is not None:
                note(ts, count)
        change = None
        today = self.reports(now, first)
        if today:
            occupied = self.count_at(today[-1], now) > 0
            start = None
            for ts in reversed(today):
                if (self.count_at(ts, now) > 0) != occupied:
                    break
                start = ts
            else:
                start = None  # unchanged since the first report: no time to give
            change = {"occupied": occupied, "ts": start}
        return {"now": now, "bucket_s": bucket, "room_id": "room1", "since": change,
                "people": [[b, peak, len(mins)] for b, (peak, mins) in sorted(seen.items())]}

    def climate(self, now, minutes):
        """One reading per bucket up to now, ending on the temperature the room tile shows (the climate board is a
        separate board, so it keeps reporting while the people sensor is offline)."""
        bucket = 60 if minutes <= 60 else 900
        midnight = (now + MYT) // 86400 * 86400 - MYT
        since = self.waste_since(now)
        points = []
        for b in range(max(midnight, now - minutes * 60) // bucket * bucket, now + 1, bucket):
            cold = since is not None and b >= since
            wobble = ((b // bucket) % 5 - 2) * 0.05 if b + bucket <= now else 0.0  # the last point is the tile's figure
            points.append([b, round((23.8 if cold else 24.6) + wobble, 2), 61.0])
        return {"now": now, "room_id": "room1", "points": points}

    def uptime(self, now):
        """GET /api/uptime as the server works it out: offline time is every gap between two reports longer than
        three report intervals, and the time since the last report once that is longer too."""
        midnight = (now + MYT) // 86400 * 86400 - MYT
        stale = 3 * INTERVAL
        sent = self.reports(now, midnight)
        rooms = {}
        if sent and now > sent[0]:
            down = sum(b - a for a, b in zip(sent, sent[1:]) if b - a > stale)
            down += now - sent[-1] if now - sent[-1] > stale else 0
            rooms["room1"] = {"first_ts": sent[0], "up_s": now - sent[0] - down, "expected_s": now - sent[0]}
        up, expected = sum(r["up_s"] for r in rooms.values()), sum(r["expected_s"] for r in rooms.values())
        return {"now": now, "since": midnight, "stale_s": stale, "rooms": rooms,
                "pct": round(100 * up / expected, 2) if expected else None}

    def labelled(self, now):
        """Two label segments of the made-up day and the reports sent during them: 107 to 105 min ago (the room stood
        empty) and 60 to 58 min ago (someone was inside). Each report carries the count the day itself gives for that time."""
        segments = [(now - 107 * 60, now - 105 * 60), (now - LABELLED_OCCUPIED[0], now - LABELLED_OCCUPIED[1])]
        points = []
        for start, end in segments:
            for ts in self.reports(now, start):
                if ts > end:
                    break
                count = self.count_at(ts, now)
                points.append({"ts": ts, "headcount_label": count, "motion_std": round(movement(ts) if count else noise(ts), 4)})
        return segments, points

    def detector(self, now):
        """GET /api/detector: the threshold rule is counting; the model facts are those of the model file in the repo."""
        try:
            m = json.loads((ROOT / "ml" / "model" / "nadi_model.json").read_text(encoding="utf-8"))
            facts = {k: m.get(k) for k in ("framework", "platform", "trained_on", "accuracy", "threshold_accuracy", "trained_at",
                                           "n_train", "n_test")}
            facts["active"] = False
        except (OSError, ValueError):
            facts = None
        return {"now": now, "mode": "rule", "threshold": THRESHOLD, "report_interval_s": INTERVAL,
                "rooms": {"room1": self.labelled(now)[1]}, "model": facts}

    def detector_summary(self, now):
        """The short form inside GET /api/info: what is counting and the model's facts, without the labelled reports."""
        d = self.detector(now)
        return {"mode": d["mode"], "threshold": d["threshold"], "model": d["model"]}

    def labels(self, now):
        segments, points = self.labelled(now)
        recent = [{"room_id": "room1", "name": NAMES["room1"], "start_ts": a, "end_ts": b,
                   "headcount": max((p["headcount_label"] for p in points if a <= p["ts"] <= b), default=0)} for a, b in segments]
        if self.many:  # thirteen labelling sessions earlier in the week: ten rows, then "Show 3 more"
            day = 86400
            recent += [{"room_id": "room1", "name": NAMES["room1"], "start_ts": now - day * 2 - i * 600, "end_ts": now - day * 2 - i * 600 + 300,
                        "headcount": i % 2} for i in range(13 - len(recent))]
            recent.sort(key=lambda r: r["start_ts"])
        return {"recent": recent[::-1], "open": {}}

    def devices(self, now):
        last = self.last_report(now)
        online = now - last <= 3 * INTERVAL
        return {"now": now, "report_interval_s": INTERVAL, "retired_hidden": 0, "devices": [
            {"device_id": "RECV-1", "service": "csi", "room_id": "room1", "rooms": ["room1"], "retired": False, "name": NAMES["room1"],
             "last_seen": last, "online": online, "simulator": False, "fw_version": "1.1.0", "uptime_s": last - self.first_report(now),
             "wifi_rssi": -52, "free_heap": 180000, "dropped": 0, "n_packets": 500},
            # the climate board is a board of its own: one report a minute, also while the people sensor is offline
            {"device_id": "CLIMATE-1", "service": "climate", "room_id": "room1", "rooms": ["room1"], "retired": False, "name": NAMES["room1"],
             "last_seen": now - now % 60, "online": True, "simulator": False, "fw_version": "1.1.0",
             "uptime_s": now - now % 60 - self.first_report(now), "wifi_rssi": -58, "free_heap": 212000, "dropped": 0, "n_packets": None}]}

    def answer(self, url):
        now = int(time.time())
        u = urlparse(url)
        q = parse_qs(u.query)
        path = u.path
        if path == "/api/rooms":
            return self.rooms(now)
        if path == "/api/rooms/room1/signal":
            return self.signal(now, int(q.get("minutes", ["5"])[0]))
        if path == "/api/signals":  # every sensing room in one answer: the overview asks this, never one room at a time
            one = self.signal(now, 5)
            return {"now": now, "minutes": 5, "threshold": one["threshold"], "rooms": {"room1": one}, "truncated": False}
        if path == "/api/incidents":
            return {"incidents": [], "active": None}
        if path == "/api/chat":  # "How many people are inside?" as the server's rule answers it, with its scope
            locked = self.state == "emergency"
            ms = self.lang == "ms"
            n = 1 if self.state in ("occupied", "emergency") else 0
            body = (f"{n} orang di dalam, di {n} bilik." if ms else f"{n} {'person' if n == 1 else 'people'} inside, in {n} room{'' if n == 1 else 's'}.")
            if locked:
                answer = ("Seluruh bangunan: " if ms else "Whole building: ") + body + (f" Mengikut tingkat: Level 4: {n} orang." if ms else f" By floor: Level 4: {n} person.")
                scope = {"kind": "building", "floor_id": None, "label": "Seluruh bangunan" if ms else "Whole building", "locked": True,
                         "reason": "Mod kecemasan aktif: jawapan meliputi seluruh bangunan." if ms else "Emergency mode is on: answers cover the whole building."}
            else:
                answer = "Level 4: " + body
                scope = {"kind": "floor", "floor_id": "f1", "label": "Level 4", "locked": False, "reason": None}
            return {"answer": answer, "source": "fallback", "model": "built-in answers", "scope": scope}
        if path == "/api/site":  # the built-in floor and the example building, as an empty site folder gives them
            example = [{"id": f"ex-{n}", "name": f"Level {n}", "level": n, "rooms": 8, "version": 0} for n in range(1, 13)]
            return {"default_floor": "f1", "editor": True, "buildings": [
                {"id": "b1", "name": BUILDING, "code": "", "example": False, "floors": [{"id": "f1", "name": "Level 4", "level": 4, "rooms": 3, "version": 0}]},
                {"id": "example", "name": "Example Tower (example data)", "code": "EX-01", "example": True, "floors": example}]}
        if path.startswith("/api/floors/") and path.endswith("/versions"):
            return {"floor_id": path.split("/")[3], "versions": [{"version": 0, "saved_ts": None, "saved_by": None, "note": "", "rooms": 3}]}
        if path.startswith("/api/floors/") and path.endswith("/plan"):
            import sys  # run as a script, the repo root is not on the path

            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from server import site  # the same plans the server draws: dashboard/plan.json and the corridor template
            floor = path.split("/")[3]
            plan = site.corridor_plan(f"ex-l{int(floor[3:]):02d}", int(floor[3:])) if floor.startswith("ex-") else site.builtin_plan()
            if not floor.startswith("ex-"):  # the server writes the live room names into the plan it answers
                for room_id, box in plan.get("rooms", {}).items():
                    if room_id in NAMES:
                        box["name"] = NAMES[room_id]
                plan["rooms"]["room1"]["capacity"] = CAPACITY
            return {"floor_id": floor, "version": 0, "saved_ts": None, "saved_by": None, "plan": plan}
        if path == "/api/info":
            return {"mode": "local", "built_with": [], "chat_model": "built-in answers", "chat_source": "rules", "building": BUILDING, "level": "Level 4", "room_names": NAMES,
                    "admin": "localhost", "headcount_source": "threshold", "detector": self.detector_summary(now),
                    "waste_minutes": WASTE_MIN, "ac_on_below_c": 26.0, "demo": False,
                    "emergency_number": None, "timezone": "Asia/Kuala_Lumpur"}
        if path == "/api/me":
            if self.viewer:
                return {"admin": False, "who": None, "rule": "token", "viewer": True, "viewer_required": False}
            return {"admin": True, "who": "localhost", "rule": "localhost", "viewer": True, "viewer_required": False}
        if path == "/api/alerts":  # the Alerts page: the same alerts the rooms answer carries
            listed = self.alerts(now)
            return {"alerts": listed, "total": len(listed), "limit": 50, "offset": 0}
        if path == "/api/history" and q.get("view") == ["people"]:
            return self.people(now, int(q.get("minutes", ["60"])[0]))
        if path == "/api/history":
            return self.history(now, int(q.get("minutes", ["60"])[0]), q.get("room", [""])[0])
        if path == "/api/uptime":
            return self.uptime(now)
        if path == "/api/detector":
            return self.detector(now)
        if path == "/api/labels":
            return self.labels(now)
        if path == "/api/board-setup":  # a documentation-style home network address, as the server would read it
            return {"ip": "192.168.1.20", "port": 1883, "configured_ip": "192.168.1.20", "mismatch": False}
        if path == "/api/devices":
            return self.devices(now)
        if path == "/api/rooms/room1/climate":
            return self.climate(now, int(q.get("minutes", ["60"])[0]))
        if path == "/api/energy":
            return self.energy(now, q.get("range", ["7d"])[0], q.get("room", [""])[0])
        if path == "/api/energy/settings":  # the server configuration's defaults, never changed in the fixture
            values = {"tariff_rm_per_kwh": TARIFF, "ac_kw": AC_KW, "ac_kw_rooms": {}, "ac_on_below_c": 26.0,
                      "waste_after_min": WASTE_MIN, "co2_kg_per_kwh": 0.75}
            return {"now": now, "settings": values, "effective_from": None, "changed_by": None, "source": "defaults",
                    "database": True, "limits": {"tariff_rm_per_kwh": [0.01, 5], "ac_kw": [0.1, 500], "ac_on_below_c": [16, 35],
                                                 "waste_after_min": [1, 240], "co2_kg_per_kwh": [0.01, 2]},
                    "max_rooms": 100, "history": [], "history_total": 0}
        return {}


def png_image_only(path):
    """Keep only the chunks that draw the image (IHDR, PLTE, tRNS, IDAT, IEND): no text, time or other metadata."""
    import struct

    data = path.read_bytes()
    out, i = [data[:8]], 8
    while i < len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        if data[i + 4:i + 8] in (b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND"):
            out.append(data[i:i + 12 + n])
        i += 12 + n
    path.write_bytes(b"".join(out))


def open_page(browser, base, fixture, width=1920, height=1080, dark=False, video_dir=None, reduced=False, path="/",
              ready="[data-room=room1]", click=None, then=None):
    """click: something to press once the page is ready (the Ask NADI button), then: what must show after it."""
    extra = {"record_video_dir": str(video_dir), "record_video_size": {"width": width, "height": height}} if video_dir else {}
    ctx = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce" if reduced else "no-preference", **extra)
    ctx.add_init_script(f"try {{ localStorage.setItem('nadiTheme', '{'dark' if dark else 'light'}') }} catch (e) {{}}")
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    history = ("/signal", "/signals", "/api/history", "/api/uptime", "/climate", "/api/detector", "/api/labels", "/api/energy")

    def reply(route):
        path = urlparse(route.request.url).path
        if fixture.db_down and any(path.endswith(h) or path.startswith(h) for h in history):  # as the server answers then
            route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "History database offline"}))
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fixture.answer(route.request.url)))
    page.route("**/api/**", reply)
    page.goto(base + path + (("&" if "?" in path else "?") + "lang=ms" if fixture.lang == "ms" else ""))
    page.locator(ready).first.wait_for()
    styled = "getComputedStyle(document.body).fontFamily.includes('Inter')"
    if not page.evaluate(styled):  # a stylesheet that failed to load would give a useless screenshot
        page.reload()
        page.locator(ready).first.wait_for()
        assert page.evaluate(styled), "the console's stylesheet did not load"
    if click:
        page.locator(click).first.click()
        page.locator(then).first.wait_for()
    return ctx, page


PEOPLE = "section:has([data-people-room])"  # the Overview's People card
PANEL = "[role=dialog]"  # the room panel
SHOTS = {  # file name: (state, options). Options beyond open_page's: lang, many, viewer, db_down (the fixture),
    # element (save that element only), type (text typed after the click, then Enter), state_after (switch the
    # fixture's state after the click) with wait (what must show then)
    "overview-all-clear": ("occupied", {}),
    "overview-all-clear-1366x768": ("occupied", {"width": 1366, "height": 768}),
    "overview-dark": ("occupied", {"dark": True}),
    "overview-ac-waste": ("waste", {}),
    "people-card-24h": ("occupied", {"path": "/?room=room1&range=24h", "ready": "[data-people-chart]", "element": PEOPLE}),
    "people-card-7d": ("occupied", {"path": "/?room=room1&range=7d", "ready": "[data-people-chart]", "element": PEOPLE}),
    "people-card-30d-dark": ("occupied", {"dark": True, "path": "/?room=room1&range=30d", "ready": "[data-people-chart]", "element": PEOPLE}),
    "overview-malay": ("waste", {"lang": "ms"}),
    "overview-sensor-offline": ("offline", {}),
    "emergency-takeover": ("emergency", {}),
    "floor-plan": ("occupied", {"path": "/floor", "ready": "main h1"}),
    "room-panel": ("occupied", {"path": "/floor?room=room1", "ready": "[data-pair]"}),
    "room-panel-dark": ("occupied", {"dark": True, "path": "/floor?room=room1", "ready": "[data-pair]"}),
    "room-no-sensor": ("occupied", {"path": "/floor?room=room3", "ready": "[data-no-sensor]"}),
    "rooms": ("waste", {"path": "/rooms", "ready": "main h1"}),
    "sensors": ("occupied", {"path": "/sensors", "ready": "main h1"}),
    "calibration": ("occupied", {"path": "/calibration", "ready": "[data-dots]"}),
    "calibration-phone": ("occupied", {"path": "/calibration", "ready": "[data-dots]", "width": 390, "height": 844}),
    "energy": ("waste", {"path": "/energy?range=30d", "ready": "[data-waste-over]"}),
    "energy-room-filter": ("waste", {"path": "/energy?range=7d&room=room1", "ready": "[data-room-chip]"}),
    "energy-settings-edit-dark": ("waste", {"dark": True, "path": "/energy?range=7d", "ready": "[data-energy-settings]",
                                            "click": "[data-edit-settings]", "then": "[data-energy-settings=edit]"}),
    "site-switcher-search": ("occupied", {"click": "#sidebar [data-building]", "then": "[data-site-panel]", "type": "level 1"}),
    "alerts-full-list": ("occupied", {"many": True, "path": "/alerts", "ready": "[data-alerts-list], main h1"}),
    "ask-nadi-scope": ("occupied", {"click": "[data-ask-open]", "then": "[data-suggestions]", "type": "How many people are inside?",
                                    "wait": "[data-line]:not([data-line=q])"}),
    "ask-nadi-emergency": ("occupied", {"click": "[data-ask-open]", "then": "[data-suggestions]", "state_after": "emergency",
                                        "wait": "[data-chat-scope=locked]"}),
    "database-offline-banner": ("occupied", {"db_down": True}),
    "plan-editor": ("occupied", {"path": "/floor/edit?floor=f1", "ready": "[data-editor-canvas]",
                                 "click": "[data-shape='room:room1']", "then": "[data-selected-room]"}),
}


def cpu_run(browser, base, seconds):
    """Leave the overview open with reports arriving every 10 s and measure the page's CPU time (Chrome DevTools
    Performance.getMetrics: TaskDuration is all main-thread work)."""
    ctx, page = open_page(browser, base, Fixture("video"))
    cdp = ctx.new_cdp_session(page)
    cdp.send("Performance.enable")

    def metrics():
        cdp.send("HeapProfiler.collectGarbage")  # count only what is still held, so a leak would show
        return {m["name"]: m["value"] for m in cdp.send("Performance.getMetrics")["metrics"]}

    page.wait_for_timeout(25000)  # past the first two reports: every one-shot element exists by now
    first, start = metrics(), time.time()
    page.wait_for_timeout(seconds * 1000)
    last, wall = metrics(), time.time() - start
    busy = last["TaskDuration"] - first["TaskDuration"]
    print(f"CPU over {wall:.0f} s: main thread busy {busy:.1f} s = {100 * busy / wall:.1f}% of one core "
          f"(script {last['ScriptDuration'] - first['ScriptDuration']:.1f} s, layout {last['LayoutDuration'] - first['LayoutDuration']:.1f} s, "
          f"style {last['RecalcStyleDuration'] - first['RecalcStyleDuration']:.1f} s); JS heap {first['JSHeapUsedSize'] / 1e6:.1f} MB -> "
          f"{last['JSHeapUsedSize'] / 1e6:.1f} MB; DOM nodes {first['Nodes']:.0f} -> {last['Nodes']:.0f}; page errors: {page.errors or 'none'}")
    ctx.close()


def frames(browser, base, out, seconds=50):
    """Close-up frames of the room with the signal line, as fast as the browser gives them: calm, then movement from
    15 s to 35 s, then calm. Each file name carries the milliseconds since the first frame."""
    out.mkdir(parents=True, exist_ok=True)
    ctx, page = open_page(browser, base, Fixture("video"), width=1920, height=1080)
    box = page.locator("[data-room=room1]").bounding_box()
    clip = {"x": box["x"] - 16, "y": box["y"] - 16, "width": box["width"] + 32, "height": box["height"] + 32}
    start = time.time()
    while time.time() - start < seconds:
        page.screenshot(path=str(out / f"{int((time.time() - start) * 1000):06d}.png"), clip=clip)
    print("saved", len(list(out.glob("*.png"))), "frames to", out)
    ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated states, e.g. A,B")
    ap.add_argument("--video", action="store_true", help="record a room tile and the live signal going calm, active, calm")
    ap.add_argument("--cpu", type=int, default=0, metavar="SECONDS", help="measure CPU with the page left open")
    ap.add_argument("--frames", default="", metavar="DIR", help="save close-up frames of the room tile for 50 s")
    ap.add_argument("--out", default="", metavar="DIR", help="save somewhere else than docs/screenshots/redesign")
    args = ap.parse_args()
    out = Path(args.out) if args.out else OUT
    want = [s for s in (args.only.split(",") if args.only else SHOTS) if s in SHOTS]
    if (args.cpu or args.video or args.frames) and not args.only:
        want = []
    out.mkdir(parents=True, exist_ok=True)
    server = serve()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        for name in want:
            state, opts = SHOTS[name]
            opts = dict(opts)
            fixture = Fixture(state, opts.pop("lang", "en"), opts.pop("many", False), opts.pop("viewer", False), opts.pop("db_down", False))
            element, typed = opts.pop("element", None), opts.pop("type", None)
            state_after, wait = opts.pop("state_after", None), opts.pop("wait", None)
            ctx, page = open_page(browser, base, fixture, **opts)
            if typed and opts.get("click") == "[data-ask-open]":  # the panel opens with its close button focused
                box = page.locator("[data-ask-panel] input, [data-ask-panel] textarea").last
                box.fill(typed)
                box.press("Enter")
            elif typed:  # the switcher's search box has the focus
                page.keyboard.type(typed)
            if state_after:
                fixture.state = state_after
            if wait:
                page.locator(wait).first.wait_for(timeout=20000)
            page.wait_for_timeout(2500)
            target = out / f"{name}.png"
            (page.locator(element).first if element else page).screenshot(path=str(target))
            png_image_only(target)
            scroll = page.evaluate("(() => { const m = document.getElementById('main'); return m ? m.scrollHeight - m.clientHeight : 0 })()")
            print(f"saved {name}.png  (main area scrolls by {scroll} px; page errors: {page.errors or 'none'})")
            ctx.close()
        if args.video:
            ctx, page = open_page(browser, base, Fixture("video"), video_dir=out)
            page.wait_for_timeout(56000)
            video = page.video
            ctx.close()
            target = out / "tile-calm-active-calm.webm"
            target.unlink(missing_ok=True)
            Path(video.path()).rename(target)
            print("saved", target.name)
        if args.frames:
            frames(browser, base, Path(args.frames))
        if args.cpu:
            cpu_run(browser, base, args.cpu)
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main()
