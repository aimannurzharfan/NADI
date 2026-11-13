"""Is the server clock right? Every CHECK_EVERY_S it asks an NTP server (NTP_SERVER, default pool.ntp.org) for the
time; the dashboard shows a warning when the difference is over MAX_OFFSET_S. Offline (no answer): the check is
skipped and nothing is shown, since a laptop demo often has no internet. NTP_CHECK=off switches it off.

A wrong clock matters here: alarm times, "last seen", reports and exports all use the server's time.
"""
import os
import socket
import struct
import threading
import time

MAX_OFFSET_S = 60
CHECK_EVERY_S = 900
NTP_EPOCH = 2208988800  # seconds from 1900 (NTP) to 1970 (Unix)
_state = {"offset_s": None, "checked": None}


def enabled():
    return os.getenv("NTP_CHECK", "on").strip().lower() not in ("off", "0", "false", "no")


def ntp_offset(server=None, port=123, timeout=2.0):
    """Seconds to add to this computer's clock to match the NTP server (SNTP, RFC 4330). Raises OSError offline."""
    server = server or os.getenv("NTP_SERVER", "pool.ntp.org")
    packet = b"\x23" + 47 * b"\0"  # version 4, mode 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = time.time()
        s.sendto(packet, (server, port))
        data, _ = s.recvfrom(512)
        t4 = time.time()
    if len(data) < 48:
        raise OSError("short NTP reply")
    def ts(offset):
        sec, frac = struct.unpack("!II", data[offset:offset + 8])
        return sec - NTP_EPOCH + frac / 2 ** 32
    t2, t3 = ts(32), ts(40)  # server receive and transmit times
    if t3 <= 0:
        raise OSError("NTP reply without a time")
    return ((t2 - t1) + (t3 - t4)) / 2


def check(server=None, port=123):
    """One check. Returns the offset in seconds, or None when offline (state then says nothing is known)."""
    try:
        offset = ntp_offset(server, port)
    except OSError:
        _state.update(offset_s=None, checked=None)
        return None
    _state.update(offset_s=round(offset, 1), checked=int(time.time()))
    if abs(offset) > MAX_OFFSET_S:
        print(f"warning: the server clock is {offset:+.0f} s off NTP ({server or os.getenv('NTP_SERVER', 'pool.ntp.org')})",
              flush=True)
    return offset


def warning():
    """{"offset_s", "checked"} when the clock is more than MAX_OFFSET_S off, else None (also when not checked)."""
    off = _state["offset_s"]
    return dict(_state) if off is not None and abs(off) > MAX_OFFSET_S else None


def reset():
    _state.update(offset_s=None, checked=None)


def start():
    def loop():
        while True:
            if enabled():
                check()
            time.sleep(CHECK_EVERY_S)

    threading.Thread(target=loop, daemon=True, name="nadi-clock").start()
