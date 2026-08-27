"""Unit tests for nx_lib.branding -- cached org-branding registry over migration
0081 (dbo.Organizations.BrandName/BrandAccentHex/BrandLogoFile).

Branding attaches to the Organization (PRVR, LKTR, ...), never to ClientCode --
see docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md "two axes".

Mocks engine_nexora_db.raw_connection() the same way tests/unit/test_mapping_config.py
does for the sibling cached-registry module.
"""

import types
from unittest.mock import MagicMock

import pytest

from nx_lib import branding


@pytest.fixture(autouse=True)
def clear_cache(app):
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


def _org_row(code="PRVR", name="Provera", accent="#336699", logo="prvr-logo.png"):
    return types.SimpleNamespace(
        organizationcode=code,
        BrandName=name,
        BrandAccentHex=accent,
        BrandLogoFile=logo,
    )


class _FakeCursor:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def execute(self, sql, *params):
        pass

    def fetchall(self):
        return self._rows


def _engine_with(rows=()):
    cur = _FakeCursor(rows=rows)
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, conn


def _dead_engine(exc):
    eng = MagicMock()
    eng.raw_connection.side_effect = exc
    return eng


def test_brand_for_org_returns_none_for_unknown_code(app, monkeypatch):
    eng, _ = _engine_with(rows=[_org_row(code="PRVR")])
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        assert branding.brand_for_org("NOPE") is None


def test_brand_for_org_returns_row_fields(app, monkeypatch):
    eng, _ = _engine_with(
        rows=[_org_row(code="PRVR", name="Provera", accent="#336699", logo="prvr-logo.png")]
    )
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        brand = branding.brand_for_org("PRVR")

    assert brand == {
        "name": "Provera",
        "accent_hex": "#336699",
        "logo_file": "prvr-logo.png",
    }


def test_registry_load_failure_returns_none_and_is_not_cached(app, monkeypatch):
    eng = _dead_engine(RuntimeError("NexoraDB down"))
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        assert branding.registry() is None
        # second call must re-query -- a failure is never cached
        assert branding.registry() is None

    assert eng.raw_connection.call_count == 2


def test_invalidate_branding_drops_cache(app, monkeypatch):
    eng, _ = _engine_with(rows=[_org_row()])
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        branding.registry()
        branding.registry()
        assert eng.raw_connection.call_count == 1

        branding.invalidate_branding()
        branding.registry()
        assert eng.raw_connection.call_count == 2


def test_missing_brand_columns_degrade_to_none(app, monkeypatch):
    """The TEST database's Organizations table predates these columns --
    the "column does not exist" error must be caught explicitly so TEST
    degrades to None instead of erroring on every request."""
    import pyodbc

    eng = _dead_engine(pyodbc.ProgrammingError("42S22", "Invalid column name 'BrandName'."))
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        assert branding.registry() is None


def test_invalid_accent_hex_is_dropped(app, monkeypatch):
    eng, _ = _engine_with(rows=[_org_row(code="PRVR", accent="not-a-hex")])
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.app_context():
        brand = branding.brand_for_org("PRVR")

    assert brand is not None
    assert brand["accent_hex"] is None


# --- the pre-session gate on the context processor (spec D2) ----------------
#
# logout() pops username/uuid/userid but leaves organizationcode in the
# session. Keying _inject_brand on organizationcode alone therefore kept
# branding the landing page after logout, complete with a broken logo <img>
# (branding_logo aborts 401 without a userid). Found in browser verification.


def test_inject_brand_is_empty_without_a_logged_in_session(app, monkeypatch):
    """No userid -> Nexora branding, even with organizationcode left behind."""
    from flask import session

    from nx_lib.hooks import _inject_brand

    eng, _ = _engine_with(rows=[_org_row(code="PRVR")])
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.test_request_context("/"):
        session["organizationcode"] = "PRVR"  # exactly what logout() leaves
        assert _inject_brand() == {"brand": {}}


def test_inject_brand_returns_the_org_brand_when_logged_in(app, monkeypatch):
    from flask import session

    from nx_lib.hooks import _inject_brand

    eng, _ = _engine_with(rows=[_org_row(code="PRVR", name="Privera")])
    monkeypatch.setattr(branding, "engine_nexora_db", eng)

    with app.test_request_context("/"):
        session["userid"] = 1
        session["organizationcode"] = "PRVR"
        assert _inject_brand()["brand"]["name"] == "Privera"
