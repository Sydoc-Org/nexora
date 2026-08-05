"""Tests for scripts/env-sync.py's three-way comparison.

The point of the script is catching a key that the repo declares but the server
never got (the SUPPORT_MAIL / issue #166 case), so that is what these pin down.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "env-sync.py"


@pytest.fixture(scope="module")
def env_sync():
    """Import the hyphenated script by path — it is not an importable module name."""
    spec = importlib.util.spec_from_file_location("env_sync", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_key_declared_in_example_but_absent_on_server_is_flagged(env_sync):
    """The whole reason the script exists."""
    f = env_sync.diff_envs(
        example={"DB_UID": "x", "SUPPORT_MAIL": "support@sydoc.ch"},
        local={"DB_UID": "x", "SUPPORT_MAIL": "a@b.ch"},
        remote={"DB_UID": "x"},
    )
    assert f["missing_on_server"] == ["SUPPORT_MAIL"]


def test_blank_example_default_is_opt_in_not_a_missing_key(env_sync):
    """`ANTHROPIC_API_KEY=` absent on the server is normal, not the deploy bug.

    Without this split the one line that matters drowns in twenty that do not.
    """
    f = env_sync.diff_envs(
        example={"ANTHROPIC_API_KEY": "", "SUPPORT_MAIL": "support@sydoc.ch"},
        local={},
        remote={},
    )
    assert f["missing_on_server"] == ["SUPPORT_MAIL"]
    assert f["missing_on_server_optional"] == ["ANTHROPIC_API_KEY"]


def test_whitespace_only_example_default_counts_as_opt_in(env_sync):
    f = env_sync.diff_envs(example={"K": "   "}, local={}, remote={})
    assert f["missing_on_server"] == []
    assert f["missing_on_server_optional"] == ["K"]


def test_differing_values_are_flagged(env_sync):
    f = env_sync.diff_envs(
        example={"DB_PWD": ""}, local={"DB_PWD": "new"}, remote={"DB_PWD": "old"}
    )
    assert f["value_differs"] == ["DB_PWD"]


def test_identical_files_report_nothing(env_sync):
    same = {"A": "1", "B": "2"}
    f = env_sync.diff_envs(example=same, local=dict(same), remote=dict(same))
    assert not any(f.values())


def test_server_only_key_is_reported_not_silently_dropped(env_sync):
    """Server-only values are why --push is dangerous; they must be visible."""
    f = env_sync.diff_envs(example={"A": ""}, local={"A": "1"}, remote={"A": "1", "LEGACY": "z"})
    assert f["undeclared_on_server"] == ["LEGACY"]


def test_absent_server_file_does_not_invent_findings(env_sync):
    f = env_sync.diff_envs(example={"A": ""}, local={"A": "1"}, remote=None)
    assert f["missing_on_server"] == []
    assert f["undeclared_on_server"] == []


def test_fingerprint_never_leaks_the_secret(env_sync):
    secret = "hunter2-super-secret"
    fp = env_sync.fingerprint(secret)
    assert secret not in fp
    assert fp.startswith("#")


def test_fingerprints_differ_for_different_secrets(env_sync):
    assert env_sync.fingerprint("a") != env_sync.fingerprint("b")


def test_fingerprint_distinguishes_empty_from_missing(env_sync):
    """'set but blank' and 'not present' are different problems."""
    assert env_sync.fingerprint("") != env_sync.fingerprint(None)


def test_read_env_returns_none_for_missing_file(env_sync, tmp_path):
    assert env_sync.read_env(tmp_path / "nope.env") is None


def test_read_env_parses_a_real_file(env_sync, tmp_path):
    p = tmp_path / "x.env"
    p.write_text("# comment\nA=1\nB=two words\n", encoding="utf-8")
    assert env_sync.read_env(p) == {"A": "1", "B": "two words"}
