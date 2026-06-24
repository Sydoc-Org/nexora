# tests/unit/test_config_ms02_docfields.py
"""MS02 doc-field DB config keys exist and default sanely.

The doc-field DB reuses the MS02 runtime host/login; only the dbname differs and
has NO default (engine degrades to None until the owner sets it).
"""

import os

import pytest

from nx_lib import config as cfg


def test_ms02_docfields_keys_exist():
    for name in (
        "MS02_DOCFIELDS_DB_HOST",
        "MS02_DOCFIELDS_DB_NAME",
        "MS02_DOCFIELDS_DB_USER",
        "MS02_DOCFIELDS_DB_PWD",
        "MS02_DOCFIELDS_DB_PORT",
    ):
        assert hasattr(cfg, name), f"missing config.{name}"


def test_ms02_docfields_name_has_no_default():
    # The doc-field dbname must NOT default to a fabricated value: when the env
    # var is unset the engine has to stay None. (Env-conditional so a box that
    # HAS it set is skipped rather than silently passing.)
    if os.environ.get("MS02_DOCFIELDS_DB_NAME"):
        pytest.skip("MS02_DOCFIELDS_DB_NAME is set; no-default contract not testable")
    assert cfg.MS02_DOCFIELDS_DB_NAME is None


def test_ms02_docfields_host_defaults_to_runtime_host():
    # HOST/USER/PWD/PORT default to the MS02 runtime values.
    assert cfg.MS02_DOCFIELDS_DB_HOST == cfg.MS02_DB_HOST
    assert cfg.MS02_DOCFIELDS_DB_USER == cfg.MS02_DB_USER
    assert cfg.MS02_DOCFIELDS_DB_PWD == cfg.MS02_DB_PWD
    assert cfg.MS02_DOCFIELDS_DB_PORT == cfg.MS02_DB_PORT
