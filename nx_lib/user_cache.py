"""Per-process TTL cache for the per-request user reads (permissions, ui_prefs).

Two before_request hooks used to hit NexoraDB on EVERY request per user —
``EXEC dbo.spGetUserPermissions`` and ``SELECT ui_prefs FROM Users`` — which at
~500 users is the single biggest DB-load multiplier (each click, each 5 s
heartbeat). PROD is one waitress process (web.config), so a process-local
cache is consistent for every request; the session-cookie race that made a
*session*-stored cache go stale (#155) does not apply here.

Staleness is bounded two ways: entries expire after ``NEXORA_USER_CACHE_TTL``
seconds (default 30; ``0`` disables the cache — the test suite runs that way),
and ``hooks._invalidate_user_cache`` drops the affected entries the moment a
user saves prefs or an admin changes anything, so changes still apply on the
very next request.

# ponytail: one process -> one dict. Move to a shared store (Redis / SQL) the
# day a second waitress process or box appears.
"""

import os
import threading
import time

_lock = threading.Lock()
_store = {}  # (kind, userid) -> (expires_at_monotonic, value)


def ttl_seconds():
    try:
        return float(os.environ.get("NEXORA_USER_CACHE_TTL", "30"))
    except ValueError:
        return 30.0


def get_or_load(kind, userid, loader):
    """Return the cached value for (kind, userid) or call ``loader()`` and cache it."""
    ttl = ttl_seconds()
    if ttl <= 0:
        return loader()
    key = (kind, str(userid))
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    value = loader()
    with _lock:
        _store[key] = (now + ttl, value)
    return value


def forget(userid):
    """Drop every cached kind for one user."""
    uid = str(userid)
    with _lock:
        for key in [k for k in _store if k[1] == uid]:
            del _store[key]


def clear():
    with _lock:
        _store.clear()
