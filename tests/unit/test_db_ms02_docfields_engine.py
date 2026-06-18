# tests/unit/test_db_ms02_docfields_engine.py
"""engine_ms02_docfields_pg exists and degrades to None without its dbname."""

import pytest

import nx_lib.db as db
from nx_lib import config as cfg


def test_engine_attr_exists():
    # The symbol must always be importable (value may be None in CI/TEST).
    assert hasattr(db, "engine_ms02_docfields_pg")


def test_engine_none_when_dbname_absent():
    # On CI/dev without MS02_DOCFIELDS_DB_NAME the engine must be None
    # (graceful-degrade, same as engine_ms02_pg / engine_ms02_stats_pg).
    if cfg.MS02_DOCFIELDS_DB_NAME:
        pytest.skip("MS02_DOCFIELDS_DB_NAME is set; graceful-degrade path not reachable")
    assert db.engine_ms02_docfields_pg is None


def test_engine_is_none_or_engine():
    eng = db.engine_ms02_docfields_pg
    assert eng is None or hasattr(eng, "raw_connection")
