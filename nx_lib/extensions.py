"""Flask extension singletons, bound to the app via init_app(app).

Splitting instantiation from binding lets blueprints import these (e.g. for
``@limiter.limit(...)`` decorators) before create_app() has been called.
"""

from flask_babel import Babel
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from itsdangerous import URLSafeTimedSerializer

from . import config as cfg
from .i18n import get_locale, get_timezone

babel = Babel()
# TODO: under IIS FastCGI each worker process gets its own in-memory rate-limit
# counter, so @limiter.limit(...) is enforced per-worker rather than globally.
# For real protection wire storage_uri to NexoraDB (SQLAlchemy) or Redis.
limiter = Limiter(key_func=get_remote_address)
cache = Cache(config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300})
csrf = CSRFProtect()

# Token signer for password-reset links. Safe to construct here because
# nexora.config has already been imported and the secret is loaded.
s = URLSafeTimedSerializer(cfg.SECRET_KEY)


def init_app(app):
    babel.init_app(app, locale_selector=get_locale, timezone_selector=get_timezone)
    limiter.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
