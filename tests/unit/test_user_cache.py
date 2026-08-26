"""nx_lib/user_cache.py + the hooks that feed and invalidate it."""

from unittest.mock import patch

from nx_lib import user_cache
from nx_lib.hooks import _invalidate_user_cache, _load_user_ui_prefs, _reload_user_permissions


def _counting_loader(value):
    calls = {"n": 0}

    def load():
        calls["n"] += 1
        return value

    return load, calls


def test_cache_serves_within_ttl_and_expires(monkeypatch):
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    load, calls = _counting_loader(["a.view"])
    now = {"t": 1000.0}
    monkeypatch.setattr(user_cache.time, "monotonic", lambda: now["t"])
    assert user_cache.get_or_load("permissions", 7, load) == ["a.view"]
    assert user_cache.get_or_load("permissions", 7, load) == ["a.view"]
    assert calls["n"] == 1  # second call served from cache
    now["t"] += 31
    user_cache.get_or_load("permissions", 7, load)
    assert calls["n"] == 2  # expired -> reloaded


def test_ttl_zero_disables_cache(monkeypatch):
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "0")
    load, calls = _counting_loader({})
    user_cache.get_or_load("ui_prefs", 7, load)
    user_cache.get_or_load("ui_prefs", 7, load)
    assert calls["n"] == 2


def test_forget_and_clear_are_scoped(monkeypatch):
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    for uid in (1, 2):
        user_cache.get_or_load("permissions", uid, lambda uid=uid: [f"u{uid}"])
        user_cache.get_or_load("ui_prefs", uid, lambda: {"theme": "dark"})
    user_cache.forget(1)
    l1, c1 = _counting_loader(["fresh"])
    l2, c2 = _counting_loader(["fresh"])
    user_cache.get_or_load("permissions", 1, l1)
    user_cache.get_or_load("permissions", 2, l2)
    assert (c1["n"], c2["n"]) == (1, 0)  # user 1 reloaded, user 2 still cached
    user_cache.clear()
    user_cache.get_or_load("permissions", 2, l2)
    assert c2["n"] == 1


def test_hooks_read_through_the_cache(app, monkeypatch):
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    with (
        patch("nx_lib.hooks.load_permissions_for_user", return_value=["x.view"]) as perms,
        patch("nx_lib.hooks.load_ui_prefs", return_value={"theme": "dark"}) as prefs,
    ):
        for _ in range(3):
            with app.test_request_context("/profile"):
                from flask import session

                session["userid"] = 42
                _reload_user_permissions()
                _load_user_ui_prefs()
                assert session["permissions"] == ["x.view"]
                assert session["ui_prefs"] == {"theme": "dark"}
    assert perms.call_count == 1
    assert prefs.call_count == 1


def test_invalidation_hook(app, monkeypatch):
    user_cache.clear()
    monkeypatch.setenv("NEXORA_USER_CACHE_TTL", "30")
    user_cache.get_or_load("permissions", 42, lambda: ["old"])
    user_cache.get_or_load("permissions", 43, lambda: ["old"])
    from flask import session

    with app.test_request_context("/profile", method="GET"):
        _invalidate_user_cache(None)
    assert user_cache.get_or_load("permissions", 42, lambda: ["new"]) == ["old"]  # GET: untouched

    with app.test_request_context("/profile/ui_prefs", method="POST"):
        session["userid"] = 42
        _invalidate_user_cache(None)
    assert user_cache.get_or_load("permissions", 42, lambda: ["new"]) == [
        "new"
    ]  # own entry dropped
    assert user_cache.get_or_load("permissions", 43, lambda: ["new"]) == ["old"]  # others kept

    with app.test_request_context("/admin/api/users/43", method="POST"):
        _invalidate_user_cache(None)
    assert user_cache.get_or_load("permissions", 43, lambda: ["new"]) == ["new"]  # admin write: all
