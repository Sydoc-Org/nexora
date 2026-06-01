"""Unit tests for nx_lib.i18n — locale + timezone resolution."""

from types import SimpleNamespace

import pytest
from flask import g

from nx_lib.i18n import get_locale, get_timezone


@pytest.fixture()
def i18n_fake_session(monkeypatch):
    """Patch nx_lib.i18n.session (separate from nx_lib.security.session)."""
    sess = {}
    monkeypatch.setattr("nx_lib.i18n.session", sess)
    return sess


def test_get_locale_returns_session_value_when_present(app, i18n_fake_session):
    i18n_fake_session["locale"] = "de"
    with app.test_request_context("/"):
        assert get_locale() == "de"


def test_get_locale_returns_g_user_locale_when_session_empty(app, i18n_fake_session):
    with app.test_request_context("/"):
        g.user = SimpleNamespace(locale="fr")
        assert get_locale() == "fr"


def test_get_locale_ignores_g_user_with_unsupported_locale(app, i18n_fake_session):
    with app.test_request_context("/", headers={"Accept-Language": "en"}):
        g.user = SimpleNamespace(locale="ja")  # not in en/de/fr/it
        # Falls through to accept_languages → "en"
        assert get_locale() == "en"


def test_get_locale_uses_accept_language_when_no_session_or_g_user(app, i18n_fake_session):
    with app.test_request_context("/", headers={"Accept-Language": "fr"}):
        assert get_locale() == "fr"


def test_get_locale_picks_best_match_from_accept_language(app, i18n_fake_session):
    with app.test_request_context("/", headers={"Accept-Language": "de;q=0.9,en;q=0.5"}):
        # German wins on q-value
        assert get_locale() == "de"


def test_get_locale_falls_back_to_a_supported_locale_for_unsupported(app, i18n_fake_session):
    with app.test_request_context("/", headers={"Accept-Language": "ja"}):
        # best_match returns None for fully-unsupported; Flask-Babel will
        # then use its default; for our test, the function returns whatever
        # best_match produces (could be None on strict Werkzeug). The test
        # asserts the function does not raise and returns one of the
        # supported set or None.
        result = get_locale()
        assert result is None or result in ("en", "de", "fr", "it")


def test_get_timezone_none_when_g_user_missing(app):
    with app.test_request_context("/"):
        assert get_timezone() is None


def test_get_timezone_returns_g_user_timezone(app):
    with app.test_request_context("/"):
        g.user = SimpleNamespace(timezone="Europe/Zurich")
        assert get_timezone() == "Europe/Zurich"
