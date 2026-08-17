"""Unit tests for nx_lib.config's dotenv load-order precedence (D-DOTENV).

nx_lib/config.py loads env/{ENVIRONMENT}.env, then falls back to a root
.env for values it doesn't define. The docstring's contract is:
OS env > env-specific file > root .env. Exercised here against
``_load_env_files`` directly with tmp files/dirs, so the real repo's env/
directory and root .env are never touched.
"""

import os

import pytest

from nx_lib.config import _load_env_files

_KEY = "NX_TEST_DOTENV_PRECEDENCE_KEY"


@pytest.fixture(autouse=True)
def _clean_test_key():
    # load_dotenv mutates os.environ directly, so monkeypatch's fixture
    # teardown (which only tracks monkeypatch.setenv/delenv calls) won't
    # see it. Clean up before and after unconditionally.
    os.environ.pop(_KEY, None)
    yield
    os.environ.pop(_KEY, None)


def _write_env_specific_and_root(tmp_path, env_specific_value, root_value):
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    (env_dir / "TEST.env").write_text(f"{_KEY}={env_specific_value}\n")
    (tmp_path / ".env").write_text(f"{_KEY}={root_value}\n")


def test_env_specific_file_wins_over_root_env(tmp_path):
    _write_env_specific_and_root(tmp_path, "from-env-specific", "from-root")

    _load_env_files(tmp_path, "TEST")

    assert os.environ[_KEY] == "from-env-specific"


def test_process_env_wins_over_both_files(tmp_path, monkeypatch):
    monkeypatch.setenv(_KEY, "from-process-env")
    _write_env_specific_and_root(tmp_path, "from-env-specific", "from-root")

    _load_env_files(tmp_path, "TEST")

    assert os.environ[_KEY] == "from-process-env"
