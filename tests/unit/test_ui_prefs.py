"""Unit tests for nx_lib.ui_prefs + the /profile/ui_prefs endpoint (issue #155)."""

from unittest.mock import patch

from nx_lib.ui_prefs import UI_PREF_CHOICES, sanitize_ui_prefs

# ---------- sanitize_ui_prefs ----------


def test_sanitize_keeps_valid_values():
    raw = {"theme": "dark", "accent": "rose", "density": "compact"}
    assert sanitize_ui_prefs(raw) == raw


def test_sanitize_drops_unknown_keys_and_values():
    assert sanitize_ui_prefs({"theme": "neon", "hack": "x", "accent": "violet"}) == {
        "accent": "violet"
    }


def test_sanitize_rejects_non_dict():
    assert sanitize_ui_prefs(None) == {}
    assert sanitize_ui_prefs(["theme", "dark"]) == {}
    assert sanitize_ui_prefs("theme=dark") == {}


def test_sanitize_rejects_non_string_values():
    assert sanitize_ui_prefs({"theme": ["dark"], "motion": 1}) == {}


def test_every_choice_round_trips():
    for key, values in UI_PREF_CHOICES.items():
        for value in values:
            assert sanitize_ui_prefs({key: value}) == {key: value}


def test_sanitize_accent_hex():
    assert sanitize_ui_prefs({"accentHex": "#1A2b3C"}) == {"accentHex": "#1a2b3c"}
    assert sanitize_ui_prefs({"accentHex": "#12345"}) == {}
    assert sanitize_ui_prefs({"accentHex": "1a2b3c"}) == {}
    assert sanitize_ui_prefs({"accentHex": "#12345g"}) == {}
    assert sanitize_ui_prefs({"accentHex": 123456}) == {}


# ---------- /profile/ui_prefs endpoint ----------


def test_ui_prefs_endpoint_requires_login(client):
    r = client.post("/profile/ui_prefs", json={"theme": "dark"})
    assert r.status_code == 401


def test_ui_prefs_endpoint_rejects_invalid_patch(client):
    with client.session_transaction() as s:
        s["userid"] = 1
        s["username"] = "tester"
    r = client.post("/profile/ui_prefs", json={"theme": "neon"})
    assert r.status_code == 400


def test_ui_prefs_endpoint_merges_and_persists(client):
    with client.session_transaction() as s:
        s["userid"] = 1
        s["username"] = "tester"
        s["ui_prefs"] = {"accent": "sky"}
    with patch("nx_lib.views.profile.save_ui_prefs", return_value=True) as save:
        r = client.post("/profile/ui_prefs", json={"theme": "dark", "bogus": "x"})
    assert r.status_code == 200
    assert r.get_json()["prefs"] == {"accent": "sky", "theme": "dark"}
    save.assert_called_once_with(1, {"accent": "sky", "theme": "dark"})
    with client.session_transaction() as s:
        assert s["ui_prefs"] == {"accent": "sky", "theme": "dark"}


def test_ui_prefs_endpoint_500_when_save_fails(client):
    with client.session_transaction() as s:
        s["userid"] = 1
        s["username"] = "tester"
    with patch("nx_lib.views.profile.save_ui_prefs", return_value=False):
        r = client.post("/profile/ui_prefs", json={"theme": "dark"})
    assert r.status_code == 500
