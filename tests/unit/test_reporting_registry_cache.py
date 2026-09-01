"""Unit tests for the 60s TTL cache around nx_lib.views.reporting's
_load_db_sources()/_load_db_metrics() (Task 7 of the beautification plan).

Mocks engine_nexora_db.raw_connection() the same way tests/unit/test_mapping_config.py
does for nx_lib.mapping_config.registry().
"""

import types
from unittest.mock import MagicMock

import pytest

from nx_lib.views import reporting as rv


@pytest.fixture(autouse=True)
def clear_cache(app):
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()
    yield
    with app.app_context():
        from nx_lib.extensions import cache

        cache.clear()


def _source_row(
    code="docprocessing",
    kind="table",
    label="Doc Processing",
    permission=None,
    engine="nexora",
    target=None,
    provider=None,
    base_object=None,
    columns_json=None,
    enabled=True,
    sort_order=100,
):
    return types.SimpleNamespace(
        Code=code,
        Kind=kind,
        Label=label,
        Permission=permission,
        Engine=engine,
        Target=target,
        Provider=provider,
        BaseObject=base_object,
        ColumnsJSON=columns_json,
        Enabled=enabled,
        SortOrder=sort_order,
    )


def _metric_row(
    code="docs_imported",
    source_id=1,
    label="Docs Imported",
    label_de=None,
    label_fr=None,
    label_it=None,
    aggregation="count",
    base_field=None,
    description=None,
    fmt=None,
    sort_order=100,
    total_mode="sum",
    anchor=None,
):
    return types.SimpleNamespace(
        Code=code,
        SourceId=source_id,
        Label=label,
        GermanLabel=label_de,
        FrenchLabel=label_fr,
        ItalianLabel=label_it,
        Aggregation=aggregation,
        BaseField=base_field,
        Description=description,
        Format=fmt,
        SortOrder=sort_order,
        TotalMode=total_mode,
        DateAnchor=anchor,
    )


class _FakeCursor:
    """Routes each execute() by table name to a canned result set, mirroring
    tests/unit/test_mapping_config.py's _FakeCursor."""

    def __init__(self, sources=(), metrics=()):
        self._sources = list(sources)
        self._metrics = list(metrics)
        self._result = []

    def execute(self, sql, *params):
        if "FROM dbo.ReportingSources" in sql:
            self._result = self._sources
        elif "FROM dbo.ReportingMetrics" in sql:
            self._result = self._metrics
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self):
        return self._result


def _engine_with(sources=(), metrics=()):
    cur = _FakeCursor(sources=sources, metrics=metrics)
    conn = MagicMock()
    conn.cursor.return_value = cur
    eng = MagicMock()
    eng.raw_connection.return_value = conn
    return eng, conn


def _dead_engine(msg="NexoraDB down"):
    eng = MagicMock()
    eng.raw_connection.side_effect = RuntimeError(msg)
    return eng


# -- _load_db_sources ---------------------------------------------------


def test_load_db_sources_caches_within_ttl(app, monkeypatch):
    eng, conn = _engine_with(sources=[_source_row()])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        rows1 = rv._load_db_sources()
        rows2 = rv._load_db_sources()

    assert rows1 == rows2
    assert rows1[0]["code"] == "docprocessing"
    eng.raw_connection.assert_called_once()
    conn.close.assert_called_once()


def test_load_db_sources_failure_is_not_cached(app, monkeypatch):
    eng = _dead_engine()
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        assert rv._load_db_sources() == []
        # a load failure must never be cached -- the next call re-queries
        assert rv._load_db_sources() == []

    assert eng.raw_connection.call_count == 2


def test_invalidate_reporting_sources_drops_cache(app, monkeypatch):
    eng, _ = _engine_with(sources=[_source_row()])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        rv._load_db_sources()
        rv._load_db_sources()
        assert eng.raw_connection.call_count == 1

        rv.invalidate_reporting_sources()
        rv._load_db_sources()
        assert eng.raw_connection.call_count == 2


def test_load_db_sources_empty_result_is_cached_as_success(app, monkeypatch):
    """An empty-but-successful load IS cached (mirrors mapping_config's contract)."""
    eng, _ = _engine_with(sources=[])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        assert rv._load_db_sources() == []
        assert rv._load_db_sources() == []

    eng.raw_connection.assert_called_once()


# -- _load_db_metrics -----------------------------------------------------


def test_load_db_metrics_caches_within_ttl(app, monkeypatch):
    eng, conn = _engine_with(metrics=[_metric_row()])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        out1 = rv._load_db_metrics()
        out2 = rv._load_db_metrics()

    assert out1 == out2
    assert "docs_imported" in out1
    eng.raw_connection.assert_called_once()
    conn.close.assert_called_once()


def test_load_db_metrics_failure_is_not_cached(app, monkeypatch):
    eng = _dead_engine()
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        assert rv._load_db_metrics() == {}
        assert rv._load_db_metrics() == {}

    assert eng.raw_connection.call_count == 2


def test_invalidate_reporting_metrics_drops_cache(app, monkeypatch):
    eng, _ = _engine_with(metrics=[_metric_row()])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        rv._load_db_metrics()
        rv._load_db_metrics()
        assert eng.raw_connection.call_count == 1

        rv.invalidate_reporting_metrics()
        rv._load_db_metrics()
        assert eng.raw_connection.call_count == 2


def test_sources_and_metrics_caches_are_independent(app, monkeypatch):
    eng, _ = _engine_with(sources=[_source_row()], metrics=[_metric_row()])
    monkeypatch.setattr(rv, "engine_nexora_db", eng)

    with app.app_context():
        rv._load_db_sources()
        rv._load_db_metrics()
        assert eng.raw_connection.call_count == 2

        # invalidating sources must not evict the metrics cache
        rv.invalidate_reporting_sources()
        rv._load_db_metrics()
        assert eng.raw_connection.call_count == 2
        rv._load_db_sources()
        assert eng.raw_connection.call_count == 3
