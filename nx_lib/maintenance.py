"""Maintenance-banner lookup and lockout helpers."""

import time

from flask import current_app

from .db import engine_nexora_db
from .security import load_permissions_for_user

MAINTENANCE_SEVERITIES = {"info", "warning", "critical"}

# Cached lookup of active blocking maintenance — TTL'd so we don't hit the DB
# on every request. Returns dict or None.
_MAINTENANCE_BLOCK_CACHE = {"expires_at": 0.0, "data": None}
_MAINTENANCE_BLOCK_TTL = 5  # seconds

_MAINTENANCE_LOCKOUT_SKIP_PATHS = (
    "/static",
    "/maintenance",
    "/api/maintenance/active",
    "/login",
    "/logout",
)


def _maintenance_iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _maintenance_row_to_dict(row, cols):
    d = dict(zip(cols, row, strict=False))
    for k in ("StartAt", "EndAt", "CreatedAt"):
        d[k] = _maintenance_iso(d.get(k))
    d["Active"] = bool(d.get("Active"))
    if "BlockAccess" in d:
        d["BlockAccess"] = bool(d.get("BlockAccess"))
    if "AnnounceMinutesBefore" in d:
        d["AnnounceMinutesBefore"] = int(d["AnnounceMinutesBefore"] or 0)
    return d


def _maintenance_parse_payload(body):
    title = (body.get("title") or "").strip()
    message = (body.get("message") or "").strip()
    start_at = (body.get("startAt") or "").strip().replace("T", " ")
    end_at = (body.get("endAt") or "").strip().replace("T", " ")
    severity = (body.get("severity") or "info").strip().lower()
    active = bool(body.get("active", True))
    block_access = bool(body.get("blockAccess", False))
    try:
        announce_minutes = max(0, min(1440, int(body.get("announceMinutesBefore") or 0)))
    except (TypeError, ValueError):
        announce_minutes = 0

    if not message:
        return None, ("message is required", 400)
    if not start_at or not end_at:
        return None, ("startAt and endAt are required", 400)
    if severity not in MAINTENANCE_SEVERITIES:
        return None, ("invalid severity", 400)
    return {
        "title": title or None,
        "message": message,
        "start_at": start_at,
        "end_at": end_at,
        "severity": severity,
        "active": 1 if active else 0,
        "block_access": 1 if block_access else 0,
        "announce_minutes": announce_minutes,
    }, None


def _get_blocking_maintenance():
    now_ts = time.time()
    if now_ts < _MAINTENANCE_BLOCK_CACHE["expires_at"]:
        return _MAINTENANCE_BLOCK_CACHE["data"]
    result = None
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 ID, Title, Message, StartAt, EndAt, Severity
            FROM MaintenanceBanner
            WHERE Active = 1 AND BlockAccess = 1
              AND StartAt <= GETDATE() AND EndAt >= GETDATE()
            ORDER BY StartAt DESC, ID DESC
        """)
        row = cursor.fetchone()
        if row:
            result = {
                "id": int(row[0]),
                "title": row[1],
                "message": row[2],
                "startAt": _maintenance_iso(row[3]),
                "endAt": _maintenance_iso(row[4]),
                "severity": row[5],
            }
    except Exception as e:
        current_app.logger.error(f"Maintenance lockout lookup failed: {e}")
        # Fail open — never lock users out due to a transient DB blip.
    finally:
        # Always return the pooled connection. Closing inside the try meant a
        # failing query (e.g. MaintenanceBanner absent in TEST) leaked a
        # connection on every request, eventually exhausting the pool.
        if conn is not None:
            conn.close()
    # Cache the outcome — including None on error — so a missing table or a
    # transient blip doesn't re-query (and re-open a connection) every request.
    _MAINTENANCE_BLOCK_CACHE["data"] = result
    _MAINTENANCE_BLOCK_CACHE["expires_at"] = now_ts + _MAINTENANCE_BLOCK_TTL
    return result


def _user_has_maintenance_bypass(userid):
    if userid is None:
        return False
    try:
        perms = load_permissions_for_user(str(userid)) or []
    except Exception as e:
        current_app.logger.error(f"Bypass perm lookup failed: {e}")
        return False
    return "admin.maintenance.bypass" in perms


def _maintenance_blocks_user(userid):
    """Returns the blocking banner if ``userid`` would be locked out, else None."""
    blocking = _get_blocking_maintenance()
    if not blocking:
        return None
    if _user_has_maintenance_bypass(userid):
        return None
    return blocking
