"""Single cached accessor for per-organization white-label branding (#98 phase 4).

Loads dbo.Organizations.BrandName / BrandAccentHex / BrandLogoFile (migration
0081) into one registry keyed by organizationcode.

Branding attaches to the Organization (the customer -- PRVR, LKTR, ...), never
to ClientCode (the runtime source -- default, ms02): those are different axes.
See docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md, "two axes".

Failure contract (mirrors nx_lib/mapping_config.py, do not weaken):
- a load error returns None from registry() and is NEVER cached (the caller
  degrades to Nexora branding);
- the TEST database's Organizations table predates these columns -- that
  specific "column does not exist" error is caught explicitly so TEST
  degrades to None instead of erroring on every request;
- an empty-but-successfully-loaded registry IS a valid success and gets
  cached.

Branding is never cached in flask.session -- that invites staleness across
admin edits and is out of scope here (see Task 10).
"""

import re

from flask import current_app

from .db import engine_nexora_db
from .extensions import cache

_CACHE_KEY = "org_branding_registry"
_TTL = 60  # seconds; admin edits should apply fast

# Reuse of nx_lib/ui_prefs.py's pattern -- do not write a second one.
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# SQL Server error codes/messages for "column does not exist" (invalid column
# name), raised by pyodbc as a ProgrammingError with SQLSTATE 42S22.
_MISSING_COLUMN_SQLSTATE = "42S22"


def _is_missing_column_error(exc: Exception) -> bool:
    """True when ``exc`` is pyodbc's "invalid column name" error -- i.e. the
    TEST database's Organizations table, which predates migration 0081."""
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], str) and args[0] == _MISSING_COLUMN_SQLSTATE:
        return True
    return "Invalid column name" in str(exc)


def registry() -> dict | None:
    """Cached (60s) {organizationcode: {"name","accent_hex","logo_file"}}.

    None on load failure -- including the TEST database's Organizations
    table, which predates the BrandName/BrandAccentHex/BrandLogoFile
    columns -- and never cached."""
    reg = cache.get(_CACHE_KEY)
    if reg is not None:
        return reg
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT organizationcode, BrandName, BrandAccentHex, BrandLogoFile "
            "FROM Organizations"
        )
        reg = {}
        for r in cur.fetchall():
            accent = r.BrandAccentHex
            if accent is not None and not _HEX_RE.match(accent):
                accent = None
            reg[r.organizationcode] = {
                "name": r.BrandName,
                "accent_hex": accent,
                "logo_file": r.BrandLogoFile,
            }
        cache.set(_CACHE_KEY, reg, timeout=_TTL)  # success-only, including empty results
        return reg
    except Exception as e:
        if _is_missing_column_error(e):
            current_app.logger.info(f"branding load: Organizations lacks brand columns: {e}")
        else:
            current_app.logger.error(f"branding load: {e}")
        return None
    finally:
        if conn:
            conn.close()


def invalidate_branding() -> None:
    """Drop the cached registry so the next registry() call re-queries."""
    cache.delete(_CACHE_KEY)


def brand_for_org(code: str) -> dict | None:
    """Branding for organization ``code``, or None on failure/unknown code."""
    reg = registry()
    if reg is None:
        return None
    return reg.get(code)
