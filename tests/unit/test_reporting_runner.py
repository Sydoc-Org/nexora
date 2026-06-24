# tests/unit/test_reporting_runner.py
"""Unit tests for nx_lib.reporting.runner.execute_definition.

The runner re-implements the view's _prepare_run for a sessionless owner; these
tests pin the metrics path (a saved definition carrying `metrics` must resolve
and aggregate exactly like an interactive run) with the view internals faked.
"""

import datetime

import nx_lib.reporting.runner as runner_mod

FAKE_CATALOG = [
    {
        "field": "doctype",
        "label": "Doc type",
        "type": "string",
        "aggregable": False,
        "sortable": True,
        "filterable": True,
        "processes": ["acme.inv"],
    },
    {
        "field": "workitem_id",
        "label": "Workitem ID",
        "type": "string",
        "aggregable": False,
        "sortable": True,
        "filterable": True,
        "grainable": False,
        "processes": ["acme.inv"],
    },
]

OWNER_PERMS = {
    "reporting.view",
    "reporting.source.docprocessing",
    "reporting.scope.process.acme.inv",
}


def _definition(**over):
    base = {
        "schemaVersion": 1,
        "source": "docprocessing",
        "visualization": "table",
        "title": "t",
        "columns": [{"field": "doctype"}],
        "metrics": [{"metric": "workitem_count"}],
        "filters": [],
        "sort": [],
        "scope": {"clients": [], "processes": []},
        "rowLimit": 100,
    }
    base.update(over)
    return base


def _patch_view_internals(monkeypatch, captured):
    from nx_lib.views import reporting as rv

    monkeypatch.setattr(
        runner_mod, "fetch_docprocessing_catalog", lambda allowed, loc: FAKE_CATALOG
    )
    monkeypatch.setattr(
        rv,
        "_get_effective_source",
        lambda s: {
            "id": "docprocessing",
            "kind": "curated",
            "provider": "docprocessing",
            "permission": "reporting.source.docprocessing",
        },
    )
    monkeypatch.setattr(
        rv,
        "_metrics_for_source",
        lambda sid: {
            "workitem_count": {"aggregation": "count_distinct", "base_field": "workitem_id"}
        },
    )
    monkeypatch.setattr(
        rv,
        "_load_process_configs",
        lambda scope: [
            {
                "process": "acme.inv",
                "table": "dbo.StatA",
                "export_col": None,
                "import_col": None,
                "condition": "",
                "workitem_col": "WorkItem",
            }
        ],
    )
    monkeypatch.setattr(
        rv, "_load_field_col_maps", lambda scope: {"acme.inv": {"doctype": "DocType"}}
    )

    def fake_execute(engine, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [("Invoice", 5)]

    monkeypatch.setattr(rv, "_execute", fake_execute)


def test_scheduled_metric_definition_resolves_and_aggregates(monkeypatch):
    captured = {}
    _patch_view_internals(monkeypatch, captured)

    cols, rows = runner_mod.execute_definition(_definition(), OWNER_PERMS, 1, "tester", "en")

    assert "COUNT(DISTINCT [workitem_id]) AS [workitem_count]" in captured["sql"]
    assert "GROUP BY [doctype]" in captured["sql"]
    assert rows == [("Invoice", 5)]


def test_scheduled_metric_definition_appends_metric_columns(monkeypatch):
    # The export columns must include the metric code, mirroring _prepare_run —
    # otherwise the emailed CSV/XLSX silently drops the aggregate column.
    captured = {}
    _patch_view_internals(monkeypatch, captured)

    cols, _rows = runner_mod.execute_definition(_definition(), OWNER_PERMS, 1, "tester", "en")

    assert [c["field"] for c in cols] == ["doctype", "workitem_count"]


def test_scheduled_zero_dimension_metric_definition_runs(monkeypatch):
    # columns may be empty when metrics are present (grand total card).
    captured = {}
    _patch_view_internals(monkeypatch, captured)

    cols, _rows = runner_mod.execute_definition(
        _definition(columns=[]), OWNER_PERMS, 1, "tester", "en"
    )

    assert "COUNT(DISTINCT [workitem_id]) AS [workitem_count]" in captured["sql"]
    assert "GROUP BY" not in captured["sql"]
    assert [c["field"] for c in cols] == ["workitem_count"]


def test_scheduled_table_source_metric_definition_resolves(monkeypatch):
    # The table-provider branch must resolve metrics exactly like docprocessing.
    from nx_lib.views import reporting as rv

    monkeypatch.setattr(
        rv,
        "_get_effective_source",
        lambda s: {
            "id": "workitems",
            "kind": "curated",
            "provider": "table",
            "permission": "reporting.source.workitems",
            "baseObject": "dbo.Workitems",
            "engine": "octo",
            "columns": [{"field": "status", "label": "Status", "type": "string"}],
        },
    )
    monkeypatch.setattr(
        rv,
        "_metrics_for_source",
        lambda sid: {"wi_count": {"aggregation": "count", "base_field": None}},
    )
    captured = {}

    def fake_execute(engine, sql, params):
        captured["sql"] = sql
        return [("Open", 3)]

    monkeypatch.setattr(rv, "_execute", fake_execute)
    monkeypatch.setattr(rv, "_CURATED_ENGINES", {"octo": object()})

    definition = _definition(
        source="workitems",
        columns=[{"field": "status"}],
        metrics=[{"metric": "wi_count"}],
    )
    cols, rows = runner_mod.execute_definition(
        definition, {"reporting.view", "reporting.source.workitems"}, 1, "tester", "en"
    )

    assert "COUNT(*) AS [wi_count]" in captured["sql"]
    assert [c["field"] for c in cols] == ["status", "wi_count"]


def test_scheduled_definition_with_relative_token_resolves_at_run_time(monkeypatch):
    from nx_lib.reporting.tokens import resolve_token

    captured = {}
    _patch_view_internals(monkeypatch, captured)
    date_catalog = [
        *FAKE_CATALOG,
        {
            "field": "import_date",
            "label": "Import date",
            "type": "string",
            "grainable": True,
            "filterable": True,
            "sortable": True,
            "aggregable": False,
            "processes": ["acme.inv"],
        },
    ]
    monkeypatch.setattr(
        runner_mod, "fetch_docprocessing_catalog", lambda allowed, loc: date_catalog
    )
    from nx_lib.views import reporting as rv

    monkeypatch.setattr(
        rv,
        "_load_process_configs",
        lambda scope: [
            {
                "process": "acme.inv",
                "table": "dbo.StatA",
                "export_col": None,
                "import_col": "ImportDate",
                "condition": "",
                "workitem_col": "WorkItem",
            }
        ],
    )

    definition = _definition(
        filters=[{"field": "import_date", "op": "between", "value": {"token": "last_month"}}]
    )
    runner_mod.execute_definition(definition, OWNER_PERMS, 1, "tester", "en")

    start, end = resolve_token({"token": "last_month"})
    end_excl = end + datetime.timedelta(days=1)
    assert ">= ?" in captured["sql"] and "< ?" in captured["sql"]
    assert "BETWEEN" not in captured["sql"]
    assert captured["params"] == [start.isoformat(), end_excl.isoformat()]
    # The caller's saved definition object still carries the token.
    assert definition["filters"][0]["value"] == {"token": "last_month"}
