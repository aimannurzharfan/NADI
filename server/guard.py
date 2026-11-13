"""Per-IP rate limits and admin token lockout, kept in Valkey/Redis so they survive a restart and are shared by every
server worker. If Valkey is offline the same rules run in memory for this process.

- Every request: a per-IP limit per bucket (see BUCKETS in server/main.py), 429 with Retry-After when over.
- Chat: CHAT_PER_MIN questions per minute per IP. Emergency toggle: EMERGENCY_PER_MIN presses per minute per IP.
- Tokens: FAIL_LIMIT wrong admin or viewer tokens in FAIL_WINDOW_S stop further guesses from that IP for LOCK_S.
  A right token still works during a lockout, so nobody can lock a warden out.

The client IP comes from server.main.client_ip: the TCP peer, or X-Forwarded-For only from TRUSTED_PROXIES.
"""
import collections
import os
import threading
import time

CHAT_PER_MIN = int(os.getenv("CHAT_PER_MIN", "10"))
EMERGENCY_PER_MIN = int(os.getenv("EMERGENCY_PER_MIN", "6"))
FAIL_LIMIT = 5
FAIL_WINDOW_S = 600
LOCK_S = 900
MAX_KEYS = 10000  # memory fallback: forget the oldest callers beyond this

USE_REDIS = True  # tests switch this off
_hits = collections.OrderedDict()  # memory fallback: (bucket, ip, window) -> count
_fails = {}
_locked = {}
_lock = threading.Lock()


def _redis():
    if not USE_REDIS:
        return None
    from server import health, store

    return store.r if health.should_try("redis") else None


def _mark_down():
    from server import health

    health.mark("redis", False)


def allow(bucket, ip, limit, window_s=60):
    """(True, 0) and count this call, or (False, seconds to wait). Fixed windows of window_s seconds."""
    now = time.time()
    window = int(now // window_s)
    wait = max(1, int((window + 1) * window_s - now) + 1)
    r = _redis()
    if r is not None:
        key = f"rl:{bucket}:{ip}:{window}"
        try:
            pipe = r.pipeline(transaction=False)
            pipe.incr(key)
            pipe.expire(key, window_s + 1)
            count = pipe.execute()[0]
            return (True, 0) if count <= limit else (False, wait)
        except Exception:
            _mark_down()
    with _lock:
        key = (bucket, ip, window)
        _hits[key] = _hits.get(key, 0) + 1
        _hits.move_to_end(key)
        while len(_hits) > MAX_KEYS:
            _hits.popitem(last=False)
        return (True, 0) if _hits[key] <= limit else (False, wait)


def locked(ip):
    """Seconds left on this IP's lockout, 0 if none."""
    r = _redis()
    if r is not None:
        try:
            ttl = r.ttl(f"lock:{ip}")
            return max(0, int(ttl)) if ttl and ttl > 0 else 0
        except Exception:
            _mark_down()
    with _lock:
        until = _locked.get(ip, 0)
        if until and until <= time.time():
            del _locked[ip]
            return 0
        return max(0, int(until - time.time()) + 1) if until else 0


def failed(ip):
    """Record a wrong token. Returns seconds locked if this failure triggered the lockout, else 0."""
    r = _redis()
    if r is not None:
        try:
            pipe = r.pipeline(transaction=False)
            pipe.incr(f"fail:{ip}")
            pipe.expire(f"fail:{ip}", FAIL_WINDOW_S)
            count = pipe.execute()[0]
            if count >= FAIL_LIMIT:
                r.set(f"lock:{ip}", 1, ex=LOCK_S)
                r.delete(f"fail:{ip}")
                return LOCK_S
            return 0
        except Exception:
            _mark_down()
    now = time.time()
    with _lock:
        q = [t for t in _fails.get(ip, []) if t > now - FAIL_WINDOW_S] + [now]
        _fails[ip] = q
        if len(q) >= FAIL_LIMIT:
            _locked[ip] = now + LOCK_S
            _fails.pop(ip, None)
            if len(_locked) > MAX_KEYS:
                for k in sorted(_locked, key=lambda k: _locked[k])[: len(_locked) - MAX_KEYS]:
                    del _locked[k]
            return LOCK_S
        if len(_fails) > MAX_KEYS:
            _fails.pop(next(iter(_fails)))
        return 0


def reset():
    """Forget every limit and lockout (tests, and scripts/reset_demo_data.py)."""
    with _lock:
        _hits.clear()
        _fails.clear()
        _locked.clear()
    r = _redis()
    if r is not None:
        try:
            for pattern in ("rl:*", "fail:*", "lock:*"):
                for key in r.scan_iter(pattern, count=500):
                    r.delete(key)
        except Exception:
            _mark_down()
