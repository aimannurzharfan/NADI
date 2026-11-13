"""Rate limits, lockouts and dependency state live in memory for the whole process: start every test clean.
Every test gets its own empty in-memory Redis (fakeredis), so no test ever reads or writes the real Valkey. Never
call monkeypatch.undo() in a test: it would undo that too. Limits are kept in memory, and incident reports go to a
temporary folder. The developer's .env is not read (see below)."""
import os
import re
import tempfile
import time
from pathlib import Path

import dotenv
import fakeredis
import pytest

# The tests give the same result on every computer: the developer's .env (calibrated thresholds, tokens, room names)
# is never read, and a setting from .env.example that is already in the shell is dropped. A test that needs a
# setting sets it itself.
dotenv.load_dotenv = lambda *args, **kwargs: False
_example = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
for _key in re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", _example, flags=re.M):
    os.environ.pop(_key, None)

os.environ.setdefault("ROOMS_CACHE_S", "0")      # every test sees fresh room state
os.environ.setdefault("DEVICE_MIN_GAP_S", "0")   # tests send reports faster than a real board
os.environ.setdefault("INCIDENT_DIR", tempfile.mkdtemp(prefix="nadi-incidents-"))
os.environ.setdefault("NTP_CHECK", "off")
os.environ.setdefault("SITE_DIR", tempfile.mkdtemp(prefix="nadi-site-"))  # empty: the built-in plan, never data/site

from server import clock, energy, guard, health, main, store  # noqa: E402

guard.USE_REDIS = False
main.ROOMS_CACHE_S = 0


@pytest.fixture(autouse=True)
def no_real_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(store, "r", fake)
    return fake


@pytest.fixture(autouse=True)
def no_duplicate_check(monkeypatch):
    monkeypatch.setattr(store, "already_seen", lambda *a: False)  # tests resend the same report on purpose


class LimiterClock:
    """The clock the rate limiter reads, shifted so that every test starts on a whole minute. The limiter counts in
    fixed one-minute windows, so a test that sends "ten allowed, then refused" would fail whenever the real clock
    crossed a minute between two of its requests. It still follows the real clock (and a test that patches
    time.time), only moved: a test would have to run for a minute to cross a window."""

    def __init__(self):
        now = time.time()
        self.shift = (now // 60 + 1) * 60 - now

    def time(self):
        return time.time() + self.shift

    def __getattr__(self, name):
        return getattr(time, name)


@pytest.fixture(autouse=True)
def limiter_clock(monkeypatch):
    shifted = LimiterClock()
    monkeypatch.setattr(guard, "time", shifted)
    return shifted


@pytest.fixture(autouse=True)
def no_stored_energy_settings(monkeypatch):
    """The energy settings are the configuration defaults and are never read from a real MySQL. A test of the
    settings puts its own database behind store.mysql and calls energy.reset()."""
    energy.reset()
    monkeypatch.setattr(energy, "delay_override_s", None)
    monkeypatch.setitem(energy._state, "next", float("inf"))
    yield
    energy.reset()


@pytest.fixture(autouse=True)
def clean_state():
    guard.reset()
    health.reset()
    clock.reset()
    main._rooms_cache.clear()
    yield
    guard.reset()
    health.reset()
    clock.reset()
