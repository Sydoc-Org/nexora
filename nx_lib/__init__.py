"""nx_lib — Flask application package.

The WSGI entry point is ``nx_main:app`` at the repo root (what waitress is
handed by IIS's HttpPlatformHandler on PROD, and what ``nx -u`` / ``flask
run`` load locally); it calls create_app() from this package.
"""

import os
from datetime import timedelta

from flask import Flask, url_for
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
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
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

    # Every template asset tag now goes through static_v() below, so the
    # ?v=<mtime> query string is what invalidates a browser's cache on
    # deploy -- safe to let Flask serve /static with a long, cacheable
    # max-age instead of the no-cache default (#191 follow-up).
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=365)

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
    api_external.register_routes(app)  # machine-to-machine API (Bearer key, no session)

    if cfg.IS_PROD:
        from .middleware import PrefixMiddleware

        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/nexora")

    return app
