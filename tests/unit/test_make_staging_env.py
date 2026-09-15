"""scripts/make-staging-env.py derives STAGING.env from PROD.env (#338)."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "make-staging-env.py"


def _load():
    spec = importlib.util.spec_from_file_location("make_staging_env", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_derive_swaps_db_names_and_mints_a_secret():
    out = _load().derive("ENVIRONMENT=PROD\nDB_NEXORA=nexora\nFLASK_SECRET_KEY=old\nDB_UID=u\n")
    lines = out.splitlines()
    assert "ENVIRONMENT=STAGING" in lines
    assert "DB_NEXORA=nexora_STAGING" in lines
    assert "DB_GENERALI=Generali_STAGING" in lines  # added when PROD.env lacks it
    assert "DB_UID=u" in lines
    assert "FLASK_SECRET_KEY=old" not in lines
    assert any(ln.startswith("FLASK_SECRET_KEY=") and len(ln) > 40 for ln in lines)
