"""Flask extension singletons, bound to the app via init_app(app).

Splitting instantiation from binding lets blueprints import these (e.g. for
``@limiter.limit(...)`` decorators) before create_app() has been called.
"""

import os

from flask import request
from flask_babel import Babel
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from itsdangerous import URLSafeTimedSerializer

from . import config as cfg
from .i18n import get_locale, get_timezone

babel = Babel()


def client_ip():
    """Rate-limit key: leftmost X-Forwarded-For hop, else the socket peer.

    Behind the PROD chain (ngrok edge -> IIS/HttpPlatformHandler -> waitress)
    the socket peer is always 127.0.0.1, so keying on it would put every user
    in ONE bucket -- ten logins a minute for the whole company. Same rule
    hooks.get_ip() applies to the CSV request log.
    """
    # ponytail: leftmost hop is client-controlled (lets a spoofer dodge his own
    # limit, never amplify onto others); tighten to waitress
    # --trusted-proxy-count once the hop count on SYAPP01 is confirmed.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or get_remote_address()


# In-memory counter: PROD is a single waitress process (see web.config), so the
# limit is global for the process and only resets on an app-pool recycle. Wire
# storage_uri to NexoraDB/Redis if a second process or box is ever added.
limiter = Limiter(key_func=client_ip)
cache = Cache(config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})
csrf = CSRFProtect()

# Token signer for password-reset links. Safe to construct here because
# nexora.config has already been imported and the secret is loaded.
s = URLSafeTimedSerializer(cfg.SECRET_KEY)


def init_app(app):
    babel.init_app(app, locale_selector=get_locale, timezone_selector=get_timezone)
    # E2E tests drive a real subprocess server and would trip the per-route
    # limits (e.g. /login "10 per minute") across a long browser session. The
    # e2e conftest sets NEXORA_DISABLE_RATELIMIT=1 so only that subprocess opts
    # out — in-process unit tests keep the limiter so their 429 assertions hold.
    if os.environ.get("NEXORA_DISABLE_RATELIMIT") == "1":
        app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
