"""nx_lib — Flask application package.

This package replaces the old monolithic app.py. The wfastcgi entry point
remains C:\\...\\nexora\\app.py which calls create_app() from this package
so IIS continues to resolve app:app unchanged.
"""

import os
from datetime import timedelta

from flask import Flask
from flask_session import Session
from flask_talisman import Talisman

from . import app_logging, extensions, hooks
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

    app_logging.init_app(app)

    if cfg.IS_PROD:
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SESSION_FILE_DIR"] = str(cfg.PATHS.session)
        app.config["SESSION_PERMANENT"] = True
        app.config["SESSION_USE_SIGNER"] = True
        Session(app)

    extensions.init_app(app)
    hooks.init_app(app)

    if cfg.IS_PROD:
        Talisman(app, content_security_policy=cfg.CSP)

    # Routes are registered via add_url_rule() (rather than Blueprint) so the
    # original endpoint names ("login", "logout", "profile", ...) are preserved
    # — every url_for(...) call in templates continues to resolve unchanged.
    from .views import (
        admin,
        api_external,
        auth,
        chat,
        core,
        dashboard,
        generali,
        invoices,
        notifications,
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
    notifications.register_routes(app)
    invoices.register_routes(app)
    chat.register_routes(app)
    api_external.register_routes(app)  # machine-to-machine API (Bearer key, no session)

    if cfg.IS_PROD:
        from .middleware import PrefixMiddleware

        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/nexora")

    return app
