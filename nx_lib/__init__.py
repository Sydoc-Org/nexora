"""nx_lib — Flask application package.

The WSGI entry point is ``nx_main:app`` at the repo root (what waitress is
handed by IIS's HttpPlatformHandler on PROD, and what ``nx -u`` / ``flask
run`` load locally); it calls create_app() from this package.
"""

import os
from datetime import timedelta

from flask import Flask, request, url_for
from flask_session import Session
from flask_talisman import Talisman

from . import app_logging, compression, extensions, hooks
from . import config as cfg

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    app = Flask(
        "nx_lib",
        template_folder=os.path.join(PROJECT_ROOT, "templates"),
        static_folder=os.path.join(PROJECT_ROOT, "static"),
        root_path=PROJECT_ROOT,
    )

    app.config["SECRET_KEY"] = cfg.SECRET_KEY

    # Applied in EVERY environment (#193): a non-PROD instance is not
    # guaranteed unreachable (ngrok tunnel, LAN, pivot), so it must never serve
    # a JS-readable / cross-site-sendable session cookie or accept an unbounded
    # upload body. SECURE stays PROD-only -- dev/INT run plain HTTP and a Secure
    # cookie would never be sent, breaking local login.
    app.config["PERMANENT_SESSION_LIFETIME"] = cfg.SESSION_LIFETIME
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Cap request bodies so an upload route can't buffer arbitrary memory into a
    # worker (#193). Sized above the largest legitimate PID xlsx / avatar.
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB

    app_logging.init_app(app)

    if cfg.IS_PROD:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = str(cfg.PATHS.session)
        app.config["SESSION_PERMANENT"] = True
        app.config["SESSION_USE_SIGNER"] = True
        Session(app)

    # Registered before the other after_request hooks so it runs LAST (Flask
    # calls them in reverse registration order) -- nothing else then reads or
    # rewrites a body that is already gzipped.
    compression.init_app(app)

    extensions.init_app(app)
    hooks.init_app(app)

    # Nonce global for inline <script nonce="{{ csp_nonce() }}"> tags (#193
    # finding 10). Talisman below overwrites this with the real per-request
    # nonce generator, but only in PROD (where Talisman/CSP is active) --
    # this no-op default keeps every template rendering the attribute
    # harmlessly (empty nonce) in dev/INT/test, where there's no CSP to
    # violate.
    app.jinja_env.globals.setdefault("csp_nonce", lambda: "")

    # NOTE: do NOT set app.config["SEND_FILE_MAX_AGE_DEFAULT"] here (final-review
    # fix, post-#191). That config applies to EVERY send_file()/send_from_directory()
    # call in the app, not just Flask's built-in /static route -- it previously
    # also stamped a public, year-long Cache-Control onto confidential workitem
    # document JPEGs (nx_lib/views/workitems.py api_get_media_raw) and onto user
    # avatars (nx_lib/views/profile.py user_avatar), which have no static_v()-style
    # cache-buster and so either leaked a "safe to cache publicly" signal for
    # confidential imagery or served a stale avatar for up to a year. The long
    # cache lifetime below is scoped to the "static" endpoint only.
    static_max_age_seconds = int(timedelta(days=365).total_seconds())

    @app.after_request
    def _static_cache_control(resp):
        # Every template asset tag goes through static_v() below, so the
        # ?v=<mtime> query string is what invalidates a browser's cache on
        # deploy -- safe to let Flask's own /static route use a long,
        # cacheable max-age (#191 follow-up). Every other send_file() /
        # send_from_directory() call site must pass its own explicit max_age
        # (see tests/unit/test_static_v_lint.py).
        if request.endpoint == "static" and resp.status_code == 200:
            resp.headers["Cache-Control"] = f"public, max-age={static_max_age_seconds}"
        return resp

    @app.after_request
    def _html_no_store(resp):
        """Never let a rendered page be cached (#354).

        HTML went out with no Cache-Control, no ETag and no Last-Modified at
        all, so a browser had nothing to go on and fell back to heuristic
        freshness -- which a home-screen shortcut, running in its own
        standalone context, applies far more eagerly than a normal tab. The
        visible symptom was a pinned nexora that kept showing the version it
        was pinned at, for days.

        The knock-on effect is the real damage. Every asset tag's `?v=<mtime>`
        cache-buster is baked into the HTML, so a stale page also pins stale
        asset URLs: the browser never even asks for the new CSS, and the
        year-long max-age on /static above -- which is only safe because the
        HTML that references it is supposed to be fresh -- keeps serving the
        old file. A deploy then appears to do nothing.

        `no-store` rather than `no-cache`: every page here is rendered for one
        signed-in user (their name, their permissions, their tenant), so none
        of it should ever be written to a shared or on-disk cache in the first
        place. That also stops a back-button press on a shared machine
        redisplaying the previous user's page after they signed out.

        setdefault, so a view that deliberately sets its own policy keeps it.
        Static assets are untouched: they are versioned, and their long
        max-age is what makes navigation fast.
        """
        if resp.mimetype == "text/html":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.template_global()
    def tabbar_window(nav, active_page, own_tenant=None, remembered=None, solo=False):
        """The phone tab bar's three slots -- see nx_lib/tabbar.py.

        A template global rather than a context processor because it needs
        `active_page`, which each page template sets with `{% set %}` just
        before including _header.html; a context processor runs too early to
        see it.
        """
        from .tabbar import tabbar_window as _win

        return _win(nav, active_page, own_tenant, remembered, solo)

    @app.template_global()
    def tenant_switcher(nav, active_page, own_tenant=None, remembered=None, solo=False):
        """The phone sheet's tenant chips -- see nx_lib/tabbar.py.

        Shares `active_tenant_code` with the tab bar, so the chip marked
        current and the pages in the bar can never disagree.
        """
        from .tabbar import tenant_switcher as _sw

        return _sw(nav, active_page, own_tenant, remembered, solo)

    @app.template_global()
    def slot_vt_name(key):
        """view-transition-name for a tab-bar slot -- see nx_lib/tabbar.py."""
        from .tabbar import slot_transition_name

        return slot_transition_name(key)

    @app.template_global()
    def static_v(filename):
        """url_for('static') with an mtime cache-buster (#191).

        The JS partials under templates/js/ now ship their behaviour as real
        files under static/js/, so the browser can cache them across
        navigations -- which only works if a deploy changes the URL. Every
        CSS/image/JS tag in templates/ uses this helper, so SEND_FILE_MAX_AGE_DEFAULT
        above is set long: the ?v= query string is what makes that safe --
        a changed asset gets a new URL, so a year-long Cache-Control never
        serves a stale file.

        ponytail: one stat() per tag per render, uncached; the OS caches the
        inode and a page carries a handful of these. Cache it if a profile
        ever says otherwise.
        """
        try:
            assert app.static_folder is not None  # always configured for this app
            version = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
        except OSError:
            version = 0
        return f"{url_for('static', filename=filename)}?v={version}"

    @app.after_request
    def _baseline_security_headers(resp):
        # Clickjacking + MIME-sniff protection in EVERY environment (#193); PROD
        # additionally gets the full Talisman CSP/HSTS below. setdefault so
        # PROD's Talisman values win where both set the same header.
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        return resp

    if cfg.IS_PROD:
        # content_security_policy_nonce_in appends a fresh 'nonce-<random>'
        # to script-src on every request and exposes it to templates via
        # csp_nonce(); every inline <script> carries nonce="{{ csp_nonce() }}"
        # so 'unsafe-inline' is no longer needed on script-src (#193 finding
        # 10 -- CSP previously provided zero XSS mitigation).
        Talisman(
            app, content_security_policy=cfg.CSP, content_security_policy_nonce_in=["script-src"]
        )

    # Routes are registered via add_url_rule() (rather than Blueprint) so the
    # original endpoint names ("login", "logout", "profile", ...) are preserved
    # — every url_for(...) call in templates continues to resolve unchanged.
    from .views import (
        admin,
        api_external,
        auth,
        core,
        dashboard,
        generali,
        profile,
        reporting,
        tenant,
        workitems,
    )

    core.register_routes(app)
    auth.register_routes(app)
    profile.register_routes(app)
    admin.register_routes(app)
    dashboard.register_routes(app)
    reporting.register_routes(app)
    workitems.register_routes(app)
    generali.register_routes(app)
    tenant.register_routes(app)  # /t/<tenant_code>/<page_key> generated tenant pages
    api_external.register_routes(app)  # machine-to-machine API (Bearer key, no session)

    if cfg.IS_PROD:
        from .middleware import PrefixMiddleware

        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/nexora")  # type: ignore[method-assign]

    return app
