"""Application file logging.

Attaches a RotatingFileHandler to ``app.logger`` so the existing
``current_app.logger.error(...)`` / ``.warning(...)`` call sites under
``nx_lib/`` land in a real file. On dev, ``bin/nx.ps1`` separately
redirects the worker's stdout/stderr to ``var/logs/system/app_*.log``;
on prod (IIS + wfastcgi) ``app.log`` is the only file the app itself
writes -- without it, ``current_app.logger`` calls silently disappear
because wfastcgi has no ``WSGI_LOG`` configured.
"""

import logging
from logging.handlers import RotatingFileHandler

from .config import PATHS

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s %(module)s:%(lineno)d %(message)s"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def init_app(app):
    log_dir = PATHS.logs / "system"
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
