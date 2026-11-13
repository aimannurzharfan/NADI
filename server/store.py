"""Redis (live state per room) and MySQL (history).

If MySQL is offline, history rows wait in memory (up to BUFFER_MAX) and are written when it comes back.
If Redis is offline, reports still go to MySQL; live counts catch up with the next report.
"""
import collections
import json
import math
import os
import threading
import time

import pymysql
import redis

from server import health, timeutil

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "127.0.0.1"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
    decode_responses=True,
    socket_connect_timeout=1, socket_timeout=2,
)

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS occupancy (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        room_id VARCHAR(64) NOT NULL,
        ts INT NOT NULL,
        headcount INT NOT NULL,
        motion_mean FLOAT, motion_std FLOAT, amp_var FLOAT, rssi_mean FLOAT, n_packets INT,
        source VARCHAR(64) NULL,
        INDEX (room_id, ts),
        INDEX occupancy_ts (ts)
    )""",
    """CREATE TABLE IF NOT EXISTS climate (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        room_id VARCHAR(64) NOT NULL,
        ts INT NOT NULL,
        temp_c FLOAT, humidity FLOAT,
        INDEX (room_id, ts)
    )""",
    # energy settings an admin saved in the console, one row per save (server/energy.py)
    """CREATE TABLE IF NOT EXISTS energy_settings (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        effective_from INT NOT NULL,
        changed_by VARCHAR(64) NOT NULL,
        tariff_rm_per_kwh DOUBLE NOT NULL, ac_kw DOUBLE NOT NULL, ac_kw_rooms TEXT NOT NULL,
        ac_on_below_c DOUBLE NOT NULL, waste_after_min DOUBLE NOT NULL, co2_kg_per_kwh DOUBLE NOT NULL,
        INDEX (effective_from)
    )""",
]
INSERT_CSI = ("INSERT INTO occupancy (room_id, ts, headcount, motion_mean, motion_std, amp_var, rssi_mean, n_packets,"
              " source) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
INSERT_CLIMATE = "INSERT INTO climate (room_id, ts, temp_c, humidity) VALUES (%s, %s, %s, %s)"
BUFFER_MAX = 5000  # about 14 hours of one room at 20 s; oldest rows are dropped first
AUDIT_KEEP = 200
DEDUP_S = 3600
_buffer = collections.deque(maxlen=BUFFER_MAX)
_buffer_lock = threading.Lock()
REDIS_ERRORS = (redis.RedisError, OSError)
MYSQL_ERRORS = (pymysql.MySQLError, OSError)
# the row itself is bad (too long, wrong type): drop it; retrying can never work and would block the buffer
ROW_ERRORS = (pymysql.err.DataError, pymysql.err.IntegrityError, pymysql.err.ProgrammingError)


def mysql():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "nadi"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "nadi"),
        autocommit=True, connect_timeout=2, read_timeout=5, write_timeout=5,
    )


def init():
    """Create the tables. MySQL being offline at start-up is not fatal: the server runs and buffers history."""
    try:
        with mysql() as conn, conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)
            # tables made before this index existed: the history query filters on ts alone
            cur.execute("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema = DATABASE() "
                        "AND table_name = 'occupancy' AND index_name = 'occupancy_ts'")
            if not cur.fetchone()[0]:
                cur.execute("CREATE INDEX occupancy_ts ON occupancy (ts)")
            # which device sent each reading, so training can tell real boards from the simulator
            cur.execute("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
                        "AND table_name = 'occupancy' AND column_name = 'source'")
            if not cur.fetchone()[0]:
                cur.execute("ALTER TABLE occupancy ADD COLUMN source VARCHAR(64) NULL")
        health.mark("mysql", True)
    except MYSQL_ERRORS as e:
        print(f"MySQL not reachable at start-up, history is buffered until it is: {e}", flush=True)
        health.mark("mysql", False)


def _write(sql, params):
    """Insert one history row now, or buffer it while MySQL is offline."""
    if health.should_try("mysql"):
        try:
            with mysql() as conn, conn.cursor() as cur:
                cur.execute(sql, params)
            health.mark("mysql", True)
            if _buffer:
                flush_buffer()
            return
        except ROW_ERRORS as e:
            print(f"history row dropped, MySQL refused it: {e}", flush=True)
            return
        except MYSQL_ERRORS:
            health.mark("mysql", False)
    with _buffer_lock:
        _buffer.append((sql, params))


def flush_buffer():
    """Write rows kept while MySQL was offline. Stops at the first failure and keeps the rest."""
    with _buffer_lock:
        if not _buffer:
            return 0
        rows = list(_buffer)
        _buffer.clear()
    done = dropped = 0
    try:
        with mysql() as conn, conn.cursor() as cur:
            for sql, params in rows:
                try:
                    cur.execute(sql, params)
                except ROW_ERRORS as e:  # one bad row must not hold up the rest
                    print(f"buffered history row dropped, MySQL refused it: {e}", flush=True)
                    dropped += 1
                done += 1
    except MYSQL_ERRORS:
        health.mark("mysql", False)
        with _buffer_lock:
            _buffer.extendleft(reversed(rows[done:]))
    if done - dropped:
        print(f"wrote {done - dropped} history rows kept while MySQL was offline", flush=True)
    return done


def buffered():
    return len(_buffer)


def already_seen(service_id, room_id, ts):
    """True if this exact report was stored before (False when Redis is offline: _live checks again)."""
    if not health.should_try("redis"):
        return False
    try:
        return r.exists(f"seen:{service_id}:{room_id}:{ts}") == 1
    except REDIS_ERRORS:
        health.mark("redis", False)
        return False


def _live(service_id, room_id, ts, mapping, ts_field):
    """Update the live hash in Redis. False = this report was already seen (duplicate). None = Redis is offline."""
    if not health.should_try("redis"):
        return None
    try:
        if not r.set(f"seen:{service_id}:{room_id}:{ts}", 1, nx=True, ex=DEDUP_S):
            health.mark("redis", True)
            return False
        r.sadd("rooms", room_id)
        last = r.hget(f"room:{room_id}", ts_field)
        if last is None or ts >= int(last):  # an older report arriving late never overwrites a newer count
            r.hset(f"room:{room_id}", mapping=mapping)
        health.mark("redis", True)
        return True
    except REDIS_ERRORS:
        health.mark("redis", False)
        return None


def save_csi(room_id, ts, headcount, p):
    """False if this exact report (room, ts) was already stored. CSI tells 0, 1, 2 or "3 or more": at_least marks
    the 3 as a lower bound. counter says which service the live count came from."""
    mapping = {"headcount": headcount, "count_ts": ts, "at_least": "1" if headcount >= 3 else "0", "counter": "csi"}
    if _live("csi", room_id, ts, mapping, "count_ts") is False:
        return False
    _write(INSERT_CSI, (room_id, ts, headcount, p.get("motion_mean"), p.get("motion_std"),
                        p.get("amp_var"), p.get("rssi_mean"), p.get("n_packets"), p.get("source")))
    return True


def save_count(room_id, ts, headcount, p):
    """An exact headcount (0 to 1000) from the "count" service. Same history table, no CSI features."""
    if _live("count", room_id, ts, {"headcount": headcount, "count_ts": ts, "at_least": "0", "counter": "count"},
             "count_ts") is False:
        return False
    _write(INSERT_CSI, (room_id, ts, headcount, None, None, None, None, None, p.get("source")))
    return True


def pending_count(room_id):
    v = r.get(f"pending_count:{room_id}")
    return int(v) if v not in (None, "") else None


def set_pending_count(room_id, count):
    """A suspicious jump waiting for the next report to confirm it (server/main.py plausible)."""
    if count is None:
        r.delete(f"pending_count:{room_id}")
    else:
        r.set(f"pending_count:{room_id}", count, ex=600)


def should_alert_suspicious(room_id):
    """At most one "suspicious reading" alert per room per hour."""
    return bool(r.set(f"suspicious_alert:{room_id}", 1, nx=True, ex=3600))


def save_climate(room_id, ts, p):
    mapping = {"temp_c": p.get("temp_c"), "humidity": "" if p.get("humidity") is None else p["humidity"],
               "climate_ts": ts}
    if _live("climate", room_id, ts, mapping, "climate_ts") is False:
        return False
    _write(INSERT_CLIMATE, (room_id, ts, p.get("temp_c"), p.get("humidity")))
    return True


def _num(h, key, cast):
    try:
        v = cast(h[key]) if h.get(key) not in (None, "") else None
    except ValueError:  # anything stored before input checks existed
        return None
    return v if v is None or math.isfinite(v) else None  # "nan" from an old bad report would break the JSON


def rooms():
    ids = sorted(r.smembers("rooms"))
    pipe = r.pipeline(transaction=False)
    for room_id in ids:
        pipe.hgetall(f"room:{room_id}")
    out = []
    for room_id, h in zip(ids, pipe.execute()):
        headcount = _num(h, "headcount", int)
        out.append({
            "room_id": room_id,
            "headcount": headcount,
            # rows stored before the flag existed came from CSI, where 3 always meant "3 or more"
            "at_least": h["at_least"] == "1" if "at_least" in h else headcount == 3,
            "count_ts": _num(h, "count_ts", int),
            "counter": "count" if h.get("counter") == "count" else "csi",  # rows from before the field: CSI
            "temp_c": _num(h, "temp_c", float),
            "humidity": _num(h, "humidity", float),
            "empty_cold_since": _num(h, "empty_cold_since", int),
            "waste_alert_ts": _num(h, "waste_alert_ts", int),
        })
    return out


def room(room_id):
    return next((x for x in rooms() if x["room_id"] == room_id), None)


def set_empty_cold_since(room_id, since):
    if since is None:
        r.hdel(f"room:{room_id}", "empty_cold_since")
    else:
        r.hset(f"room:{room_id}", "empty_cold_since", since)


def set_waste_alert_ts(room_id, ts):
    r.hset(f"room:{room_id}", "waste_alert_ts", ts)


DAY_OFFSET_S = 8 * 3600  # daily buckets start at midnight Malaysia time (UTC+8, no daylight saving)


def _offset(bucket):
    """Buckets start on whole steps of Malaysian time: a day at midnight, 3 hours at 00:00, 03:00, 06:00."""
    return DAY_OFFSET_S % bucket if bucket else 0


def history(since, bucket=None, room_id=None):
    """{room_id: [[ts, headcount], ...]} from MySQL, oldest first. With bucket (seconds), one point per bucket:
    the highest headcount in it (for safety the peak matters, not the average). Daily buckets follow Malaysian days."""
    out = {}
    where, args = "ts >= %s", [since]
    if room_id:
        where, args = where + " AND room_id = %s", args + [room_id]
    with mysql() as conn, conn.cursor() as cur:
        if bucket:
            off = _offset(bucket)
            cur.execute(f"SELECT room_id, FLOOR((ts + %s) / %s) * %s - %s AS b, MAX(headcount) FROM occupancy "
                        f"WHERE {where} GROUP BY room_id, b ORDER BY b", [off, bucket, bucket, off, *args])
        else:
            cur.execute(f"SELECT room_id, ts, headcount FROM occupancy WHERE {where} ORDER BY ts", args)
        for rid, ts, headcount in cur.fetchall():
            out.setdefault(rid, []).append([int(ts), int(headcount)])
    return out


def people_history(room_id, since, bucket):
    """[[bucket start, peak headcount, minutes occupied], ...] for one room, oldest first. Minutes occupied: the
    distinct minutes of the bucket with at least one report above 0, so the report interval does not matter.
    Buckets with no report are left out. Read only."""
    off = _offset(bucket)
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT FLOOR((ts + %s) / %s) * %s - %s AS b, MAX(headcount), "
                    "COUNT(DISTINCT CASE WHEN headcount > 0 THEN FLOOR(ts / 60) END) FROM occupancy "
                    "WHERE room_id = %s AND ts >= %s GROUP BY b ORDER BY b", (off, bucket, bucket, off, room_id, since))
        return [[int(b), int(peak), int(minutes)] for b, peak, minutes in cur.fetchall()]


def last_change(room_id, since):
    """(occupied, ts): whether the room's latest stored report has someone inside, and the time of the first report
    of that unbroken state, looking back to `since`. ts is None when the state never changed in that time; (None,
    None) when the room has no report at all. Read only."""
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT ts, headcount FROM occupancy WHERE room_id = %s ORDER BY ts DESC LIMIT 1", (room_id,))
        rows = cur.fetchall()
        if not rows:
            return None, None
        occupied = int(rows[0][1]) > 0
        other = "headcount = 0" if occupied else "headcount > 0"
        cur.execute(f"SELECT ts FROM occupancy WHERE room_id = %s AND ts >= %s AND {other} ORDER BY ts DESC LIMIT 1",
                    (room_id, since))
        rows = cur.fetchall()
        if not rows:
            return occupied, None
        cur.execute("SELECT ts FROM occupancy WHERE room_id = %s AND ts > %s ORDER BY ts LIMIT 1", (room_id, int(rows[0][0])))
        rows = cur.fetchall()
        return occupied, int(rows[0][0]) if rows else None


def coldest(room_id, since, bucket):
    """{bucket start: lowest temperature} for one room, buckets as in history()."""
    off = _offset(bucket)
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT FLOOR((ts + %s) / %s) * %s - %s AS b, MIN(temp_c) FROM climate WHERE room_id = %s AND ts >= %s "
                    "AND temp_c IS NOT NULL GROUP BY b", (off, bucket, bucket, off, room_id, since))
        return {int(b): float(t) for b, t in cur.fetchall() if t is not None}


def climate_history(room_id, since, bucket=None):
    """[[ts, temp_c, humidity], ...] for one room, oldest first (bucket averages when bucket is set)."""
    with mysql() as conn, conn.cursor() as cur:
        if bucket:
            off = _offset(bucket)
            cur.execute("SELECT FLOOR((ts + %s) / %s) * %s - %s AS b, ROUND(AVG(temp_c), 2), ROUND(AVG(humidity), 1) FROM climate "
                        "WHERE room_id = %s AND ts >= %s GROUP BY b ORDER BY b", (off, bucket, bucket, off, room_id, since))
        else:
            cur.execute("SELECT ts, temp_c, humidity FROM climate WHERE room_id = %s AND ts >= %s ORDER BY ts",
                        (room_id, since))
        return [[int(ts), None if t is None else float(t), None if h is None else float(h)] for ts, t, h in cur.fetchall()]


def report_gaps(since, stale):
    """{room_id: [first_ts, last_ts, down_s]} for every room with a stored report since `since`: its first and last
    report, and the seconds it spent offline between them, which is every gap between two reports in a row that is
    longer than `stale` (the same rule that marks a sensor offline). For the sensor uptime figure. Read only."""
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT room_id, MIN(ts), MAX(ts), COALESCE(SUM(CASE WHEN gap > %s THEN gap ELSE 0 END), 0) FROM "
                    "(SELECT room_id, ts, ts - LAG(ts) OVER (PARTITION BY room_id ORDER BY ts) AS gap FROM occupancy "
                    "WHERE ts >= %s) AS g GROUP BY room_id", (stale, since))
        return {rid: [int(first), int(last), int(down)] for rid, first, last, down in cur.fetchall()}


SIGNAL_MAX_ROWS = 720  # an hour of one room at one report every 5 s


def signal_history(room_id, since, skip_sources=()):
    """[[ts, motion_std, headcount], ...] for one room, oldest first: the stored CSI reports only (rows from the
    "count" service carry no motion figure). skip_sources: device IDs to leave out (the simulator)."""
    where, args = "room_id = %s AND ts >= %s AND motion_std IS NOT NULL", [room_id, since]
    if skip_sources:
        marks = ", ".join(["%s"] * len(skip_sources))
        where += f" AND (source IS NULL OR source NOT IN ({marks}))"
        args += list(skip_sources)
    with mysql() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT ts, motion_std, headcount FROM occupancy WHERE {where} ORDER BY ts DESC LIMIT %s",
                    [*args, SIGNAL_MAX_ROWS])
        rows = cur.fetchall()
    return [[int(ts), float(std), int(count)] for ts, std, count in reversed(rows) if math.isfinite(float(std))]


SIGNALS_MAX_ROWS = 6000  # 64 rooms x 10 minutes at one report every 10 s, with room to spare


def signals_history(since, skip_sources=(), limit=SIGNALS_MAX_ROWS):
    """{room_id: [[ts, motion_std, headcount], ...]} for EVERY room since `since`, oldest first, in one query: the
    overview's sparklines, sensing lines and live signal chart share it, so the number of rooms never multiplies the
    number of queries. The newest `limit` rows are read. skip_sources: device IDs to leave out (the simulator)."""
    where, args = "ts >= %s AND motion_std IS NOT NULL", [since]
    if skip_sources:
        marks = ", ".join(["%s"] * len(skip_sources))
        where += f" AND (source IS NULL OR source NOT IN ({marks}))"
        args += list(skip_sources)
    with mysql() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT room_id, ts, motion_std, headcount FROM occupancy WHERE {where} ORDER BY ts DESC LIMIT %s",
                    [*args, int(limit)])
        rows = cur.fetchall()
    out = {}
    for room_id, ts, std, count in reversed(rows):
        if math.isfinite(float(std)):
            out.setdefault(room_id, []).append([int(ts), float(std), int(count)])
    return out


LABELLED_MAX_ROWS = 2000  # per room: the newest labelled reports are plenty for the calibration chart


def labelled_reports(room_id, since, until):
    """[[ts, motion_std, source], ...] for one room between two times, oldest first: the stored CSI reports that the
    calibration page sets against the label segments. The caller decides which sources count."""
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT ts, motion_std, source FROM occupancy WHERE room_id = %s AND ts >= %s AND ts <= %s "
                    "AND motion_std IS NOT NULL ORDER BY ts DESC LIMIT %s", [room_id, since, until, LABELLED_MAX_ROWS])
        rows = cur.fetchall()
    return [[int(ts), float(std), src] for ts, std, src in reversed(rows) if math.isfinite(float(std))]


WASTE_HOUR_KEEP_S = 2 * 86400  # RM per hour, for the Energy page's "Today" chart


def waste_keep_s():
    """How long a day total is kept: the history retention (90 days by default), and at least 61 days, so the Energy
    page can set the last 30 days against the 30 before."""
    return (max(60, retention_days()) + 1) * 86400


def _waste_key(now, room_id=None, unit="rm"):
    """waste_rm / waste_kwh / waste_co2 : day [: room]. The day is the Malaysian day, whatever the server's zone."""
    day = timeutil.day(now)
    return f"waste_{unit}:{day}" + (f":{room_id}" if room_id else "")


def add_waste_today(rm, now, room_id=None, kwh=0.0, co2_kg=0.0):
    """Add an ended waste stretch to the day's totals (building, and the room when given) in RM, kWh and kg CO2.
    Each amount was worked out at the rates in force during the stretch, so a later rate change leaves it alone."""
    for unit, amount in (("rm", rm), ("kwh", kwh), ("co2", co2_kg)):
        if amount > 0:
            for key in [_waste_key(now, None, unit)] + ([_waste_key(now, room_id, unit)] if room_id else []):
                r.incrbyfloat(key, amount)
                r.expire(key, waste_keep_s())


def _hour_key(ts, room_id=None):
    """waste_rm_h : day : hour [: room], the Malaysian day and hour the RM was spent in."""
    return f"waste_rm_h:{timeutil.day(ts)}:{timeutil.local(ts).hour:02d}" + (f":{room_id}" if room_id else "")


def add_waste_hours(pieces, room_id=None):
    """Add [(ts, rm)]: each part of an ended stretch in the hour it ran (building total, and the room when given)."""
    for ts, rm in pieces:
        if rm > 0:
            for key in [_hour_key(ts)] + ([_hour_key(ts, room_id)] if room_id else []):
                r.incrbyfloat(key, rm)
                r.expire(key, WASTE_HOUR_KEEP_S)


def waste_hours(now, room_id=None):
    """RM per hour of today (24 values, 00:00 first) from stretches that already ended: the building, or one room."""
    start = timeutil.midnight(now)
    return [float(v or 0) for v in r.mget([_hour_key(start + h * 3600, room_id) for h in range(24)])]


def waste_days_kwh(now, days, room_ids):
    """{room_id: [kWh of the day `days - 1` days ago, ..., kWh of today]} in one read; None for a day stored in RM
    only (or with no waste)."""
    room_ids = list(room_ids)
    if not room_ids:
        return {}
    keys = [_waste_key(now - d * 86400, room_id, "kwh") for room_id in room_ids for d in range(days - 1, -1, -1)]
    values = [None if v is None else float(v) for v in r.mget(keys)]
    return {room_id: values[i * days:(i + 1) * days] for i, room_id in enumerate(room_ids)}


def waste_days_rm(now, days, room_ids):
    """{room_id: [RM of the day `days - 1` days ago, ..., RM of today]} in one read."""
    room_ids = list(room_ids)
    if not room_ids:
        return {}
    keys = [_waste_key(now - d * 86400, room_id) for room_id in room_ids for d in range(days - 1, -1, -1)]
    values = [float(v or 0) for v in r.mget(keys)]
    return {room_id: values[i * days:(i + 1) * days] for i, room_id in enumerate(room_ids)}


def first_report_ts():
    """The time of the first report still in the history, or None when there is none."""
    with mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT MIN(ts) FROM occupancy")
        row = cur.fetchone()
    return None if not row or row[0] is None else int(row[0])


def waste_day(now, days_ago=0, room_id=None):
    """RM from waste stretches that ended on that day (total, or one room)."""
    return float(r.get(_waste_key(now - days_ago * 86400, room_id)) or 0)


def waste_day_extra(now, days_ago=0, room_id=None):
    """(kWh, kg CO2) stored for that day; each is None for a day that was stored in RM only."""
    ts = now - days_ago * 86400
    kwh, co2 = r.mget(_waste_key(ts, room_id, "kwh"), _waste_key(ts, room_id, "co2"))
    return (None if kwh is None else float(kwh)), (None if co2 is None else float(co2))


def seed_waste_extra(now, room_id, kwh, co2_kg):
    """Give a day total that holds RM only its kWh and CO2 (only where none is stored yet)."""
    r.set(_waste_key(now, room_id, "kwh"), kwh, ex=waste_keep_s(), nx=True)
    r.set(_waste_key(now, room_id, "co2"), co2_kg, ex=waste_keep_s(), nx=True)


def waste_today(now):
    """RM from air conditioning waste stretches that already ended today. Ongoing stretches are added by the caller."""
    return float(r.get(_waste_key(now)) or 0)


def mark_iotda_push(ts):
    r.set("iotda_last_push", ts, ex=3600)


def iotda_push_recent():
    return r.exists("iotda_last_push") == 1


# --- board health, for the Sensors page: the latest report per device ---

def save_device(device_id, service_id, room_id, ts, health):
    r.sadd("devices", device_id)
    r.sadd(f"device_rooms:{device_id}", room_id)  # every room this device reports for (the simulator covers several)
    r.sadd(f"device_services:{device_id}", service_id)  # and every service (the simulator sends csi and climate)
    r.hset(f"device:{device_id}", mapping={"service": service_id, "room_id": room_id, "last_seen": ts,
                                            **{k: v for k, v in health.items()}})


def forget_devices(ids):
    for device_id in ids:
        r.srem("devices", device_id)
        r.delete(f"device:{device_id}", f"device_rooms:{device_id}", f"device_services:{device_id}")


def devices():
    ids = sorted(r.smembers("devices"))
    pipe = r.pipeline(transaction=False)
    for device_id in ids:
        pipe.hgetall(f"device:{device_id}")
        pipe.smembers(f"device_rooms:{device_id}")
        pipe.smembers(f"device_services:{device_id}")
    res = pipe.execute()
    out = []
    for device_id, h, rooms_, services in zip(ids, res[0::3], res[1::3], res[2::3]):
        out.append({
            "rooms": sorted(rooms_ or ({h["room_id"]} if h.get("room_id") else set())),
            "services": sorted(services or ({h["service"]} if h.get("service") else set())),
            "device_id": device_id, "service": h.get("service"), "room_id": h.get("room_id"),
            "last_seen": _num(h, "last_seen", int), "fw_version": h.get("fw_version"),
            "uptime_s": _num(h, "uptime_s", int), "wifi_rssi": _num(h, "wifi_rssi", int),
            "free_heap": _num(h, "free_heap", int), "dropped": _num(h, "dropped", int),
            "n_packets": _num(h, "n_packets", int),
        })
    return out


# --- emergency: kept in Redis so it survives a server restart ---

def emergency():
    """{"on", "since", "drill", "id"}: drill is True for a practice run; id names the incident (or drill) record."""
    h = r.hgetall("emergency")
    on = bool(h.get("since"))
    return {"on": on, "since": int(h["since"]) if on else None, "drill": on and h.get("kind") == "drill",
            "id": h.get("id") if on else None}


def start_emergency(now, by, kind="real", incident_id=None):
    """Switch on. True only for the one call that did it: a second warden pressing at the same moment gets False
    and the first start time and kind stay (HSETNX is atomic in Redis)."""
    if r.hsetnx("emergency", "since", now):
        r.hset("emergency", mapping={"on": "1", "by": by, "kind": "drill" if kind == "drill" else "real",
                                     "id": incident_id or ""})
        return True
    return False


def end_emergency():
    """Switch off. Returns the state that was ended ({"since", "by"}), or None if it was already off."""
    pipe = r.pipeline(transaction=True)
    pipe.hgetall("emergency")
    pipe.delete("emergency")
    h, deleted = pipe.execute()
    return h if deleted and h.get("since") else None


def audit(entry):
    """Who started or ended an emergency, newest first, last AUDIT_KEEP kept."""
    r.lpush("audit", json.dumps(entry, ensure_ascii=False))
    r.ltrim("audit", 0, AUDIT_KEEP - 1)


def audit_log():
    return [json.loads(x) for x in r.lrange("audit", 0, AUDIT_KEEP - 1)]


# --- demo reset and history retention ---

DEMO_KEYS = ("rooms", "alerts", "alert_ack", "iotda_last_push")
DEMO_PATTERNS = ("room:*", "waste_rm:*", "waste_rm_h:*", "waste_kwh:*", "waste_co2:*", "seen:*", "pending_count:*", "suspicious_alert:*",
                 "devrate:*")


def clear_demo_data(keep=None, now=None):
    """Empty history (MySQL), live counts, alerts and air conditioning waste totals so a demo starts clean.
    Keeps the audit log, the emergency state, devices and labels. `keep` is {room_id: [(start_ts, end_ts or None,
    ...), ...]} (the label segments): the stored reports of a room inside one of its segments stay, so the labelled
    reports on the Calibration page survive the reset. An open segment runs until `now`.
    Returns {"redis_keys", "occupancy", "climate", "kept"}."""
    spans = [(room, int(seg[0]), int(seg[1]) if seg[1] else int(now or time.time()))
             for room, segs in sorted((keep or {}).items()) for seg in segs]
    n = r.delete(*DEMO_KEYS)
    for pattern in DEMO_PATTERNS:
        keys = list(r.scan_iter(pattern, count=500))
        for i in range(0, len(keys), 500):
            n += r.delete(*keys[i:i + 500])
    with _buffer_lock:
        _buffer.clear()
    rows = {"kept": 0}
    with mysql() as conn, conn.cursor() as cur:
        rows["climate"] = cur.execute("DELETE FROM climate")
        if not spans:
            rows["occupancy"] = cur.execute("DELETE FROM occupancy")
        else:
            # one pass marks nothing: rows inside a segment are simply left out of the DELETE
            inside = " OR ".join(["(room_id = %s AND ts >= %s AND ts <= %s)"] * len(spans))
            args = [v for span in spans for v in span]
            rows["occupancy"] = cur.execute(f"DELETE FROM occupancy WHERE NOT ({inside})", args)
            cur.execute("SELECT COUNT(*) FROM occupancy")
            rows["kept"] = int(cur.fetchone()[0])
    return {"redis_keys": n, **rows}


def retention_days():
    return max(1, int(os.getenv("HISTORY_RETENTION_DAYS", "90")))


def delete_old_history(now=None, batch=5000):
    """Delete history rows older than HISTORY_RETENTION_DAYS, in batches so MySQL stays responsive."""
    cutoff = int(now or time.time()) - retention_days() * 86400
    done = 0
    with mysql() as conn, conn.cursor() as cur:
        for table in ("occupancy", "climate"):
            while True:
                n = cur.execute(f"DELETE FROM {table} WHERE ts < %s LIMIT %s", (cutoff, batch))
                done += n
                if n < batch:
                    break
    return done


def start_retention():
    """Once a day (first run a minute after start-up): delete history older than HISTORY_RETENTION_DAYS (default 90)."""
    def loop():
        time.sleep(60)
        while True:
            if health.should_try("mysql"):
                try:
                    n = delete_old_history()
                    if n:
                        print(f"deleted {n} history rows older than {retention_days()} days", flush=True)
                except MYSQL_ERRORS as e:
                    print(f"history clean-up skipped, MySQL error: {e}", flush=True)
            time.sleep(86400)

    threading.Thread(target=loop, daemon=True, name="nadi-retention").start()
