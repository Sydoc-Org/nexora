"""API-key (Bearer) authentication for the external machine-to-machine API.

Deliberately separate from nx_lib/security.py: everything there reads the
Flask session (and its test seam monkeypatches nx_lib.security.session as a
plain dict); this module is session-free by design and never redirects.

Keys are random 32-byte tokens (secrets.token_urlsafe(32), issued by
scripts/new-api-key.py); dbo.ApiKeys (migration 0038) stores only the
SHA-256 hex digest. High-entropy keys make bcrypt unnecessary; matching is
constant-time via hmac.compare_digest over the enabled-key list (a handful
of rows in v1 -- revisit if the table ever grows large).

Error contract (all JSON, no login redirect, no i18n -- machine-facing):
  401 missing/malformed header, unknown key, OR disabled key (+
      WWW-Authenticate: Bearer). Uniform on purpose: the lookup filters
      Enabled = 1, so a revoked key is indistinguishable from a
      never-issued one -- no existence oracle on an external surface.
  503 NexoraDB unreachable during lookup (auth fails CLOSED -- deliberate
      deviation from the dashboard helpers' fail-open pattern).
"""

import hashlib
import hmac
from functools import wraps

from flask import current_app, g, jsonify, request

from .db import engine_nexora_db


def hash_api_key(raw_key):
    """SHA-256 hex digest of the raw Bearer token (the stored form). Must
    stay in sync with scripts/new-api-key.py, which duplicates these two
    lines to avoid importing nx_lib (engine creation at import time needs
    live env config)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _parse_process_list(raw):
    """Comma-separated ProcessList column -> clean list of ProcessName strings."""
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _match_key(raw_key):
    """Return the ENABLED dbo.ApiKeys row whose KeyHash matches raw_key, or None.

    Fetches every enabled row (WHERE Enabled = 1 -- disabled keys behave
    exactly like unknown ones, see module docstring) and compares per-row
    with hmac.compare_digest so the comparison is constant-time in Python
    (a WHERE KeyHash = ? lookup would compare inside the index instead).
    Raises on DB failure (the decorator turns that into a 503 -- fail closed).
    """
    presented = hash_api_key(raw_key)
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ID, KeyHash, ClientCode, ProcessList FROM dbo.ApiKeys WHERE Enabled = 1"
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    for row in rows:
        if hmac.compare_digest(str(row.KeyHash).strip(), presented):
            return row
    return None


def _touch_last_used(key_id):
    """Best-effort LastUsedAt stamp; never fails the request."""
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE dbo.ApiKeys SET LastUsedAt = SYSUTCDATETIME() WHERE ID = ?",
                [key_id],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.warning(f"ApiKeys LastUsedAt update failed: {e}")


def require_api_key(f):
    """Decorator: authenticate the request via 'Authorization: Bearer <key>'.

    On success sets g.api_client = {"key_id", "client_code", "processes"}
    and calls the view. No session is read or written.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            return (
                jsonify({"error": "Missing or malformed Authorization header"}),
                401,
                {"WWW-Authenticate": "Bearer"},
            )
        raw_key = auth[7:].strip()
        try:
            row = _match_key(raw_key)
        except Exception as e:
            current_app.logger.error(f"ApiKeys lookup failed: {e}")
            return jsonify({"error": "Auth backend unavailable"}), 503
        if row is None:
            return (
                jsonify({"error": "Invalid API key"}),
                401,
                {"WWW-Authenticate": "Bearer"},
            )
        _touch_last_used(row.ID)
        g.api_client = {
            "key_id": row.ID,
            "client_code": row.ClientCode,
            "processes": _parse_process_list(row.ProcessList),
        }
        return f(*args, **kwargs)

    return wrapper
