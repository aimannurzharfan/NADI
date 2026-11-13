"""NADI_MODE: "local" (default, no Huawei Cloud calls at all) or "huawei" (IoTDA, DCS, RDS, SMN, MaaS from .env).

Read at call time, not import time, so tests and .env changes take effect without code edits.
"""
import os

from server import plan

MODES = ("local", "huawei")


def mode():
    m = os.getenv("NADI_MODE", "local").strip().lower() or "local"
    if m not in MODES:
        raise ValueError(f"NADI_MODE must be one of {MODES}, got {m!r}")
    return m


def is_huawei():
    return mode() == "huawei"


def is_local_host(host):
    return host in ("127.0.0.1", "localhost", "::1")


def room_names(raw=None):
    """ROOM_NAMES=room1:Lab 2,room2:Hall A -> {"room1": "Lab 2", "room2": "Hall A"}.
    Display only: room IDs in data, topics and the database never change. Bad or empty entries are skipped."""
    raw = os.getenv("ROOM_NAMES", "") if raw is None else raw
    names = {}
    for part in raw.split(","):
        room_id, sep, name = part.partition(":")
        room_id, name = room_id.strip(), name.strip()
        if sep and room_id and name:
            names[room_id] = name[:40]
    return names


def room_name(room_id, names=None):
    """What a room is called: ROOM_NAMES first, then the name on the floor plan, and only then the room ID."""
    return (room_names() if names is None else names).get(room_id) or plan.room_names().get(room_id) or room_id


def display_names():
    """Every room that has a name, for the console: the floor plan's names, overridden by ROOM_NAMES."""
    return {**plan.room_names(), **room_names()}


def building_name():
    return os.getenv("BUILDING_NAME", "").strip() or "Demo Building"


def level_name():
    return os.getenv("LEVEL_NAME", "").strip() or "Level 4"


class _Tee:
    """Writes to the console and, line by line, to a rotating log file."""

    def __init__(self, stream, handler):
        self.stream, self.handler, self.part = stream, handler, ""

    def write(self, s):
        import logging

        self.stream.write(s)
        self.part += s
        while "\n" in self.part:
            line, self.part = self.part.split("\n", 1)
            self.handler.emit(logging.LogRecord("nadi", logging.INFO, "", 0, line, None, None))
        return len(s)

    def flush(self):
        self.stream.flush()
        self.handler.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def log_to_file():
    """LOG_FILE=logs/nadi.log: also keep the console output in a file, rotated at LOG_MAX_MB (default 10) with 5 old
    files kept, so a long-running server never fills the disk."""
    import logging
    import logging.handlers
    import sys
    from pathlib import Path

    path = os.getenv("LOG_FILE", "").strip()
    if not path or isinstance(sys.stdout, _Tee):
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=int(float(os.getenv("LOG_MAX_MB", "10")) * 2 ** 20),
                                                   backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    sys.stdout = _Tee(sys.stdout, handler)
    sys.stderr = _Tee(sys.stderr, handler)


def utf8_console():
    """Windows consoles and redirected logs default to cp1252, which garbles the degree sign. Force UTF-8."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
