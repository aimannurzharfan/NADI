"""Time: everything is stored as Unix seconds (UTC by definition) and shown in Malaysia time (Asia/Kuala_Lumpur).

The server computer's own time zone never matters: day totals, alert times, exports and reports all use Malaysia
time. Malaysia has no daylight saving, so a fixed UTC+8 is the fallback when the tz database is missing.
"""
import datetime

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Kuala_Lumpur")
except Exception:  # Windows without the tzdata package
    TZ = datetime.timezone(datetime.timedelta(hours=8), "MYT")

TZ_NAME = "Asia/Kuala_Lumpur"


def local(ts):
    return datetime.datetime.fromtimestamp(int(ts), TZ)


def day(ts):
    """"2026-11-03": the Malaysian calendar day of ts."""
    return local(ts).strftime("%Y-%m-%d")


def midnight(ts):
    """Unix time of the start of ts's calendar day in Malaysia."""
    return int(local(ts).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def clock(ts):
    """"07:45:00" in Malaysia time."""
    return local(ts).strftime("%H:%M:%S")


def stamp(ts):
    """"2026-11-03 07:45:00" in Malaysia time (exports and reports say it is Malaysia time)."""
    return local(ts).strftime("%Y-%m-%d %H:%M:%S")


def duration(s):
    """"4:05" or "1:02:03", like the dashboard timer."""
    s = max(0, int(s))
    h, m, x = s // 3600, s // 60 % 60, s % 60
    return (f"{h}:{m:02d}" if h else str(m)) + f":{x:02d}"


def utc_iso(ts):
    """"2026-11-02T23:45:00Z": the stored instant, for machine-readable files."""
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
