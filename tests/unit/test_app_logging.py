"""Unit tests for nx_lib.app_logging — file handler wiring."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def test_logger_has_rotating_file_handler(app):
    """create_app -> app_logging.init_app should have attached a
    RotatingFileHandler pointing at var/logs/system/app.log."""
    rotating = [h for h in app.logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) >= 1
    paths = [Path(h.baseFilename) for h in rotating]
    assert any(p.name == "app.log" for p in paths)
    assert any("logs" in p.parts for p in paths)


def test_logger_level_is_at_least_info(app):
    """init_app sets app.logger.setLevel(INFO)."""
    assert app.logger.level <= logging.INFO


def test_handler_writes_when_logger_is_called(app):
    """Emit a unique marker through app.logger.info and verify it lands in
    the underlying file."""
    marker = "test-marker-app_logging-12345"
    app.logger.info(marker)
    rotating = next(h for h in app.logger.handlers if isinstance(h, RotatingFileHandler))
    rotating.flush()
    body = Path(rotating.baseFilename).read_text(encoding="utf-8", errors="ignore")
    assert marker in body


def test_handler_uses_max_bytes_rotation(app):
    """The handler is configured with maxBytes=10 MiB."""
    rotating = next(h for h in app.logger.handlers if isinstance(h, RotatingFileHandler))
    assert rotating.maxBytes == 10 * 1024 * 1024


def test_handler_uses_backup_count(app):
    rotating = next(h for h in app.logger.handlers if isinstance(h, RotatingFileHandler))
    assert rotating.backupCount == 5


def test_handler_formatter_includes_level_and_message(app):
    """The formatter string should embed asctime + levelname + message."""
    rotating = next(h for h in app.logger.handlers if isinstance(h, RotatingFileHandler))
    fmt = rotating.formatter._fmt
    assert "%(asctime)s" in fmt
    assert "%(levelname)s" in fmt
    assert "%(message)s" in fmt
