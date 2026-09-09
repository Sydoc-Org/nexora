"""Unit tests for the SQL-sandbox per-target authorization (Octopus 2nd target).

`_authorize_sql_target` is the gate that makes the Octopus runtime DB require its
own `reporting.sql.target.octopus.use` grant on top of the base `reporting.sql.run`
that all live-SQL routes already enforce. `has_permission` reads the session, so
it is monkeypatched here — no TEST access profile holds SQL-run-without-octopus.
"""

import pytest

from nx_lib.views import reporting
from nx_lib.views.reporting import _shared

# `_authorize_sql_target` and its internal `has_permission` call both live in
# _shared.py now (beautify-phase-2a, Task 2) and call each other from there --
# monkeypatching has_permission on the package re-export would not reach that
# internal call, so it is patched on `_shared` directly.


def test_statistics_target_allowed_with_base_perm(monkeypatch):
    monkeypatch.setattr(_shared, "has_permission", lambda p: p == "reporting.sql.run")
    reporting._authorize_sql_target("statistics")  # no raise


def test_octopus_target_denied_without_target_perm(monkeypatch):
    # Has the base SQL-run perm but not the Octopus target perm.
    monkeypatch.setattr(_shared, "has_permission", lambda p: p == "reporting.sql.run")
    with pytest.raises(PermissionError):
        reporting._authorize_sql_target("octopus")


def test_octopus_target_allowed_with_target_perm(monkeypatch):
    monkeypatch.setattr(_shared, "has_permission", lambda p: True)
    reporting._authorize_sql_target("octopus")  # no raise


def test_unknown_target_is_noop(monkeypatch):
    # Unknown targets are left for _run_sql to reject as a 400, not a 403 here.
    monkeypatch.setattr(_shared, "has_permission", lambda p: False)
    reporting._authorize_sql_target("bogus")  # no raise


def test_octopus_is_a_registered_target():
    assert "octopus" in reporting._SQL_TARGETS
    assert reporting._SQL_TARGET_PERMISSION["octopus"] == "reporting.sql.target.octopus.use"


def test_generali_target_denied_without_target_perm(monkeypatch):
    # Every non-Statistics database needs its own grant on top of the base one.
    monkeypatch.setattr(_shared, "has_permission", lambda p: p == "reporting.sql.run")
    with pytest.raises(PermissionError):
        reporting._authorize_sql_target("generali")


def test_generali_is_a_registered_target():
    assert "generali" in reporting._SQL_TARGETS
    assert reporting._SQL_TARGET_PERMISSION["generali"] == "reporting.sql.target.generali.use"


def test_nexora_is_not_a_target():
    """NexoraDB holds the bcrypt password hashes and TOTP secrets. It must not
    be a sandbox target at any permission level -- _run_sql rejects unknown
    targets with a 400, and there is deliberately no permission that adds it."""
    assert "nexora" not in reporting._SQL_TARGETS
    assert "nexora" not in reporting._SQL_TARGET_PERMISSION


def test_every_target_names_the_database_it_reads():
    """The Advanced target picker labels itself from _SQL_TARGET_DB, so a target
    added without an entry here would render as a blank option."""
    assert set(reporting._SQL_TARGET_DB) == reporting._SQL_TARGETS


def test_code_registry_has_one_sql_source_per_target():
    from nx_lib.reporting.sources import code_sources

    sql = [s for s in code_sources() if s["kind"] == "sql"]
    assert {s["target"] for s in sql} == reporting._SQL_TARGETS
    # Each carries the per-target permission the gate enforces, so a registry
    # row and the gate can never disagree about who may reach a database.
    for s in sql:
        assert s["permission"] == reporting._SQL_TARGET_PERMISSION[s["target"]]
