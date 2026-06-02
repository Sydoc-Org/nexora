"""Unit tests for the SQL-sandbox per-target authorization (Octopus 2nd target).

`_authorize_sql_target` is the gate that makes the Octopus runtime DB require its
own `reporting.sql.target.octopus` grant on top of the base `reporting.sql.run`
that all live-SQL routes already enforce. `has_permission` reads the session, so
it is monkeypatched here — no TEST access profile holds SQL-run-without-octopus.
"""

import pytest

from nx_lib.views import reporting


def test_statistics_target_allowed_with_base_perm(monkeypatch):
    monkeypatch.setattr(reporting, "has_permission", lambda p: p == "reporting.sql.run")
    reporting._authorize_sql_target("statistics")  # no raise


def test_octopus_target_denied_without_target_perm(monkeypatch):
    # Has the base SQL-run perm but not the Octopus target perm.
    monkeypatch.setattr(reporting, "has_permission", lambda p: p == "reporting.sql.run")
    with pytest.raises(PermissionError):
        reporting._authorize_sql_target("octopus")


def test_octopus_target_allowed_with_target_perm(monkeypatch):
    monkeypatch.setattr(reporting, "has_permission", lambda p: True)
    reporting._authorize_sql_target("octopus")  # no raise


def test_unknown_target_is_noop(monkeypatch):
    # Unknown targets are left for _run_sql to reject as a 400, not a 403 here.
    monkeypatch.setattr(reporting, "has_permission", lambda p: False)
    reporting._authorize_sql_target("bogus")  # no raise


def test_octopus_is_a_registered_target():
    assert "octopus" in reporting._SQL_TARGETS
    assert reporting._SQL_TARGET_PERMISSION["octopus"] == "reporting.sql.target.octopus"
