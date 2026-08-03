"""Per-user UI preferences (theme, accent, motion, entrance, density, sidebar).

Stored as a small JSON blob in ``dbo.Users.ui_prefs`` and mirrored into
``session['ui_prefs']`` once per session — same idiom as ``Users.locale``.
Values are allowlisted server-side; unknown keys or values are dropped.
"""

import json

from flask import current_app

from .db import engine_nexora_db

# Allowlist: key -> valid values. Absence of a key means "client default"
# (theme falls back to the browser's localStorage, everything else to the
# first value here).
UI_PREF_CHOICES = {
    "theme": ("light", "dark", "system"),
    "accent": ("indigo", "violet", "emerald", "amber", "rose", "sky"),
    "motion": ("full", "reduced"),
    "entrance": ("rise", "fade", "none"),
    "density": ("comfortable", "compact"),
    "sidebar": ("auto", "pinned"),
}


def sanitize_ui_prefs(raw):
    """Keep only known keys carrying allowed values."""
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in UI_PREF_CHOICES and v in UI_PREF_CHOICES[k]}


def load_ui_prefs(userid):
    """Read stored prefs from dbo.Users; {} when unset or unparsable."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ui_prefs FROM Users WHERE userid = ?", [userid])
        row = cursor.fetchone()
        cursor.close()
        if row and row[0]:
            return sanitize_ui_prefs(json.loads(row[0]))
    except Exception as e:
        current_app.logger.error(f"load_ui_prefs error: {e}")
    finally:
        if conn:
            conn.close()
    return {}


def save_ui_prefs(userid, prefs):
    """Persist the (already sanitized) prefs dict as JSON."""
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET ui_prefs = ? WHERE userid = ?",
            [json.dumps(prefs, separators=(",", ":")), userid],
        )
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        current_app.logger.error(f"save_ui_prefs error: {e}")
        return False
    finally:
        if conn:
            conn.close()
