"""Unit tests for nx_lib.workitems.query -- pure Python, no Flask/session/
request. Every external dependency (DB engines, the MS02 resolver,
fetch_merged_page, the cache, a logger) is injected by the test, mirroring
how nx_lib/views/workitems.py wires the real ones in."""

import logging

import pytest

from nx_lib import mapping_config
from nx_lib.mapping_config import FieldMapping, ProcessSource
from nx_lib.workitems.query import (
    docfield_suggestions_any_field,
    get_workitems_data,
    ms02_pid_specs,
    ms02_prepared_docs_processes,
)


class _FakeCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value


class _FakeArgs:
    """Minimal stand-in for werkzeug's ImmutableMultiDict, covering just the
    .get/.getlist calls get_workitems_data makes."""

    def __init__(self, values=None, lists=None):
        self._values = values or {}
        self._lists = lists or {}

    def get(self, key, default=None, type=None):
        v = self._values.get(key, default)
        return type(v) if (type and v is not None) else v

    def getlist(self, key):
        return self._lists.get(key, [])


def _fm(field_key, column, process="sydoc.test_proc", client="default", column_type=None):
    return FieldMapping(
        client=client, process=process, field_key=field_key, column=column, column_type=column_type
    )


def _ps(process, table, alias="t", join_condition=None, time_filter="1=1", client="default"):
    return ProcessSource(
        client=client,
        process=process,
        table=table,
        alias=alias,
        join_condition=join_condition or f"{alias}.ID = twi.id",
        time_filter=time_filter,
        suggestion_time_filter=None,
        export_column=None,
        import_column=None,
        workitem_column=None,
        extra_condition=None,
        id_column_type=None,
    )


def _base_scope(**overrides):
    scope = {
        "allowed": {"default.sydoc.test_proc"},
        "can_docfields": False,
        "sensitive_blocked": set(),
        "can_status": True,
        "can_deleted": False,
        "can_stage": True,
        "can_search_id": True,
        "can_dates": True,
    }
    scope.update(overrides)
    return scope


@pytest.fixture
def logger():
    return logging.getLogger("test-workitems-query")


def test_ms02_pid_specs_empty_target_processes_short_circuits():
    assert ms02_pid_specs([]) == []


def test_ms02_pid_specs_builds_spec_from_mapping(monkeypatch):
    monkeypatch.setattr(
        mapping_config,
        "mappings_for",
        lambda client, procs, field_keys=None: [
            _fm("pid", "PID", process="sydoc.05_PDBS", client="ms02")
        ],
    )
    monkeypatch.setattr(
        mapping_config,
        "sources_for",
        lambda client, procs=None: [
            _ps(
                "sydoc.05_PDBS",
                'public."T"',
                alias="d",
                join_condition="d.WorkItemID = twi.id",
                client="ms02",
            )
        ],
    )
    specs = ms02_pid_specs(["sydoc.05_PDBS"])
    assert specs == [('public."T"', "WorkItemID", "PID", None, None, None)]


def test_ms02_prepared_docs_processes_dedupes_and_sorts(monkeypatch):
    monkeypatch.setattr(
        mapping_config,
        "mappings_for",
        lambda client, procs, field_keys=None: [
            _fm("pid", "PID", process="sydoc.06_ABC", client="ms02"),
            _fm("pid", "PID", process="sydoc.05_PDBS", client="ms02"),
            _fm("pid", "PID", process="sydoc.05_PDBS", client="ms02"),
        ],
    )
    assert ms02_prepared_docs_processes() == ["sydoc.05_PDBS", "sydoc.06_ABC"]


def test_get_workitems_data_returns_process_name_without_touching_session(logger):
    """The core never writes to session -- it hands the resolved process
    name back for the (Flask-aware) caller to persist."""
    captured = {}

    def _fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    result = get_workitems_data(
        _FakeArgs({"prcfW": "all"}),
        _base_scope(),
        export_all=False,
        valid_db_columns=[],
        activity_ignore_map={},
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        resolve_ms02_docfield_ids=lambda *a, **k: None,
        fetch_merged_page=_fetch_merged_page,
        cache=_FakeCache(),
        logger=logger,
        export_max_rows=100_000,
        workitem_stages=("Import", "Extraction", "Validation", "Delivery"),
    )
    assert result["process_name"] == "all"
    assert result["workitems"] == []
    assert result["pagination"]["perPage"] == 40
    assert captured["filt"].docfield_ids is None
    assert captured["filt"].ms02_docfield_ids is None


def test_get_workitems_data_active_docfield_search_fails_closed_without_mapping(
    logger, monkeypatch
):
    """An active doc-field pair with no usable mapping anywhere must resolve
    to an empty (not unconstrained) allow-set for both legs."""
    monkeypatch.setattr(mapping_config, "mappings_for", lambda client, procs, field_keys=None: [])
    monkeypatch.setattr(mapping_config, "sources_for", lambda client, procs=None: [])

    def _fetch_merged_page(filt, offset, per_page):
        return [], 0, []

    result = get_workitems_data(
        _FakeArgs(
            {"prcfW": "all"},
            {"docfield": ["unmapped"], "docvalue": ["x"], "docop": ["contains"]},
        ),
        _base_scope(can_docfields=True),
        export_all=False,
        valid_db_columns=["unmapped"],
        activity_ignore_map={},
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        resolve_ms02_docfield_ids=lambda *a, **k: None,
        fetch_merged_page=_fetch_merged_page,
        cache=_FakeCache(),
        logger=logger,
        export_max_rows=100_000,
        workitem_stages=("Import", "Extraction", "Validation", "Delivery"),
    )
    assert result["workitems"] == []


def test_get_workitems_data_deleted_status_hidden_without_permission(logger):
    """scope['can_deleted'] False -> 'Deleted' must not resolve to a status
    code (Status<>2 stays the effective filter, enforced by WorkitemFilter/
    fetch_merged_page, not asserted here directly)."""
    captured = {}

    def _fetch_merged_page(filt, offset, per_page):
        captured["filt"] = filt
        return [], 0, []

    get_workitems_data(
        _FakeArgs({"prcfW": "all", "status": "Deleted"}),
        _base_scope(can_deleted=False),
        export_all=False,
        valid_db_columns=[],
        activity_ignore_map={},
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        resolve_ms02_docfield_ids=lambda *a, **k: None,
        fetch_merged_page=_fetch_merged_page,
        cache=_FakeCache(),
        logger=logger,
        export_max_rows=100_000,
        workitem_stages=("Import", "Extraction", "Validation", "Delivery"),
    )
    assert captured["filt"].status_code is None


def test_docfield_suggestions_any_field_empty_columns_returns_empty_list(logger):
    result = docfield_suggestions_any_field(
        ["sydoc.test_proc"],
        [],
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        cache=_FakeCache(),
        logger=logger,
    )
    assert result == []


def test_docfield_suggestions_any_field_cache_hit_skips_resolution(logger, monkeypatch):
    cache = _FakeCache()
    cache.store["docfield_vals_any_sydoc.test_proc_validationuser"] = [("alice", "validationuser")]

    def _must_not_run(*a, **k):
        raise AssertionError("mapping_config must not be queried on a cache hit")

    monkeypatch.setattr(mapping_config, "mappings_for", _must_not_run)
    result = docfield_suggestions_any_field(
        ["sydoc.test_proc"],
        ["validationuser"],
        engine_statistics_db=None,
        engine_ms02_docfields_pg=None,
        cache=cache,
        logger=logger,
    )
    assert result == [("alice", "validationuser")]
