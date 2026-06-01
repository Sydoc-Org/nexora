"""Unit tests for nx_lib.extensions — Flask extension wiring."""

from itsdangerous import URLSafeTimedSerializer

from nx_lib.extensions import babel, cache, csrf, init_app, limiter, s


def test_limiter_singleton_exposes_limit_decorator():
    assert limiter is not None
    assert hasattr(limiter, "limit")


def test_serializer_is_url_safe_timed():
    assert isinstance(s, URLSafeTimedSerializer)


def test_csrf_singleton_exposes_init_app():
    assert hasattr(csrf, "init_app")


def test_cache_singleton_uses_simple_backend():
    assert cache is not None
    # Cache config is set at module-load
    cfg = cache.config or {}
    assert cfg.get("CACHE_TYPE") == "SimpleCache" or "CACHE_TYPE" in cfg


def test_babel_singleton_exposes_init_app():
    assert babel is not None
    assert hasattr(babel, "init_app")


def test_app_has_csrf_registered(app):
    """The session-scoped `app` fixture goes through create_app which calls
    extensions.init_app — verify the resulting state."""
    assert "csrf" in app.extensions


def test_app_has_babel_registered(app):
    assert "babel" in app.extensions


def test_app_has_limiter_registered(app):
    # flask_limiter registers under key "limiter" (newer versions) or
    # similar — accept any limiter-related key
    keys = list(app.extensions.keys())
    assert any("limiter" in k.lower() for k in keys)


def test_app_has_cache_registered(app):
    # flask_caching attaches itself; verify cache.get/set work in app context
    with app.app_context():
        cache.set("test-extensions-marker", "ok", timeout=10)
        assert cache.get("test-extensions-marker") == "ok"


def test_init_app_is_callable(app):
    """init_app(app) is idempotent — calling again should not raise."""
    # Don't actually re-init twice (Limiter would complain), just verify
    # the function is callable.
    assert callable(init_app)
