"""Unit tests for AI schema serialization (DB injected as a fake cursor)."""

import logging

from nx_lib.reporting import ai_schema


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, sql, *params):
        self.executed = sql
        return self

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _rows(*triples):
    # (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE)
    return [
        type("R", (), dict(TABLE_SCHEMA=s, TABLE_NAME=t, COLUMN_NAME=c, DATA_TYPE=d))()
        for (s, t, c, d) in triples
    ]


def test_serialize_target_groups_columns_by_table():
    conn = _FakeConn(
        _rows(
            ("dbo", "Workitems", "Id", "int"),
            ("dbo", "Workitems", "Status", "nvarchar"),
            ("dbo", "Users", "UserId", "int"),
        )
    )
    text, _ = ai_schema.serialize_target("statistics", lambda: conn)
    assert "dbo.Workitems" in text and "Id int" in text and "Status nvarchar" in text
    assert "dbo.Users" in text and "UserId int" in text
    assert conn.closed is True


def test_serialize_schema_respects_char_budget_and_logs(monkeypatch, caplog):
    conn = _FakeConn(_rows(*[("dbo", f"T{i}", "C", "int") for i in range(200)]))
    with caplog.at_level(logging.INFO):
        text, truncated = ai_schema.serialize_schema(
            targets={"statistics": (lambda: conn)},
            curated=[],
            char_budget=200,
        )
    assert len(text) <= 400  # budget + a small truncation marker
    assert truncated is True
    assert "truncated" in text.lower()
    assert "truncat" in caplog.text.lower()


def test_serialize_schema_flags_per_target_cap_truncation():
    n = ai_schema.MAX_TABLES_PER_TARGET + 20
    conn = _FakeConn(_rows(*[("dbo", f"T{i}", "C", "int") for i in range(n)]))
    text, truncated = ai_schema.serialize_schema(
        targets={"statistics": (lambda: conn)},
        curated=[],
        char_budget=100000,  # high budget so only the per-target cap fires
    )
    assert truncated is True
    assert "more tables truncated" in text


def test_serialize_schema_includes_curated_catalogs():
    curated = [
        {
            "label": "Generali — PDQM",
            "fields": [
                {"field": "Process", "type": "string"},
                {"field": "Outcome", "type": "string"},
            ],
        }
    ]
    text, _ = ai_schema.serialize_schema(targets={}, curated=curated, char_budget=10000)
    assert "Generali" in text and "Process" in text and "Outcome" in text


def test_serialize_curated_marks_sources_builder_only():
    # Curated (table-provider) sources in the schema block live on databases that
    # run_sql cannot reach (it only targets the statistics/octopus RO engines). The
    # serializer must say so explicitly, or the explain-data agent drafts
    # `SELECT ... FROM <source id>` against a run_sql target and gets a 208
    # "invalid object name" it can't recover from.
    curated = [
        {
            "label": "Generali — PDQM Report",
            "fields": [{"field": "Outcome", "type": "string"}],
        }
    ]
    text, _ = ai_schema.serialize_schema(targets={}, curated=curated, char_budget=10000)
    assert "build_definition" in text  # the tool it MUST use
    assert "run_sql" in text  # explicitly names the tool it must NOT use
    assert "builder-only" in text.lower()
    # fields and label still present so build_definition can ground on them
    assert "Generali" in text and "Outcome" in text


def test_serialize_sources_catalog_lists_ids_fields_and_flags():
    sources = [
        {
            "id": "gen_pdqm",
            "label": "Generali — PDQM",
            "fields": [
                {"field": "Outcome", "type": "string", "filterable": True, "sortable": True},
                {"field": "Qty", "type": "number", "filterable": False, "sortable": True},
            ],
            "processes": ["p1", "p2"],
        }
    ]
    text, truncated = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert "gen_pdqm" in text and "Generali — PDQM" in text
    assert "Outcome" in text and "string" in text
    assert "filterable" in text and "sortable" in text
    assert "p1" in text and "p2" in text  # caller's allowed scope
    assert truncated is False


def test_serialize_sources_catalog_shows_label_with_key():
    # docprocessing fields carry an internal KEY plus a human LABEL. The serializer
    # must show both as `key "Label"` so the model can map a NL question to a field
    # yet still emit the validator-checked key. The label is dropped when == key.
    sources = [
        {
            "id": "docproc",
            "label": "Document Processing",
            "fields": [
                {
                    "field": "documenttype",
                    "label": "Document Type",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                },
                # label == field -> rendered as the bare key (no redundant quotes)
                {"field": "Outcome", "label": "Outcome", "type": "string"},
            ],
            "processes": [],
        }
    ]
    text, _ = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert 'documenttype "Document Type":string' in text
    assert "Outcome:string" in text
    assert '"Outcome"' not in text  # no redundant key=="label" quoting


def test_serialize_sources_catalog_truncates_and_logs(caplog):
    big = [
        {
            "id": f"s{i}",
            "label": f"S{i}",
            "fields": [{"field": "F", "type": "string", "filterable": True, "sortable": True}],
            "processes": [],
        }
        for i in range(500)
    ]
    text, truncated = ai_schema.serialize_sources_catalog(big, char_budget=300)
    assert len(text) <= 400
    assert truncated is True
    assert "truncated" in text.lower()


def test_serialize_metrics_catalog_lists_blessed_metrics():
    from nx_lib.reporting.ai_schema import serialize_metrics_catalog

    metrics = [
        {
            "code": "doc_count",
            "label": "Document count",
            "aggregation": "count",
            "base_field": None,
            "source_id": "docprocessing",
        },
        {
            "code": "pages_sum",
            "label": "Total pages",
            "aggregation": "sum",
            "base_field": "pages",
            "source_id": "docprocessing",
        },
    ]
    text = serialize_metrics_catalog(metrics)
    assert "METRIC doc_count" in text
    assert "count(*) on docprocessing" in text
    assert "sum(pages) on docprocessing" in text


def test_serialize_schema_includes_metrics_block():
    metrics = [
        {
            "code": "doc_count",
            "label": "Document count",
            "aggregation": "count",
            "base_field": None,
            "source_id": "docprocessing",
        },
    ]
    text, _ = ai_schema.serialize_schema(targets={}, curated=[], metrics=metrics, char_budget=10000)
    assert "METRIC doc_count" in text
    assert "# Canonical metrics" in text


def test_serialize_schema_metrics_none_by_default():
    # Existing callers pass no metrics kwarg; must not raise and must produce same output
    text, truncated = ai_schema.serialize_schema(targets={}, curated=[], char_budget=10000)
    assert "# Canonical metrics" not in text
    assert truncated is False


def test_serialize_sources_catalog_marks_grainable_fields():
    sources = [
        {
            "id": "docprocessing",
            "label": "Doc Processing",
            "fields": [
                {
                    "field": "import_date",
                    "label": "Import date",
                    "type": "date",
                    "filterable": True,
                    "sortable": True,
                    "grainable": True,
                }
            ],
            "processes": [],
        }
    ]
    text, _tr = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert "grainable" in text


def test_catalog_humanizes_process_ids():
    sources = [
        {
            "id": "docprocessing",
            "label": "Doc processing",
            "fields": [
                {
                    "field": "docsource",
                    "label": "Document Source",
                    "type": "string",
                    "filterable": True,
                }
            ],
            "processes": ["privera.03_Invoice_New", "compass.01_Invoice_SAP"],
        }
    ]
    text, truncated = ai_schema.serialize_sources_catalog(sources)
    assert 'privera.03_Invoice_New ("privera Invoice New")' in text
    assert 'compass.01_Invoice_SAP ("compass Invoice SAP")' in text
    assert truncated is False


def test_serialize_sources_catalog_lists_source_metrics():
    sources = [
        {
            "id": "docprocessing",
            "label": "Doc Processing",
            "fields": [{"field": "client", "type": "string", "filterable": True, "sortable": True}],
            "processes": [],
            "metrics": [
                {
                    "code": "doc_count",
                    "label": "Documents",
                    "aggregation": "count",
                    "base_field": None,
                }
            ],
        }
    ]
    text, _tr = ai_schema.serialize_sources_catalog(sources, char_budget=10000)
    assert 'metrics: doc_count "Documents" = count(*)' in text


def test_metricless_source_is_marked_no_aggregation():
    sources = [
        {
            "id": "workitems",
            "label": "Workitems (Octo)",
            "fields": [
                {
                    "field": "wid",
                    "label": "Workitem ID",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                }
            ],
            "processes": [],
            "metrics": [],
        }
    ]
    text, truncated = ai_schema.serialize_sources_catalog(sources)
    assert truncated is False
    assert "metrics: none" in text
    assert "cannot aggregate" in text


def test_source_with_metrics_keeps_its_metrics_line():
    sources = [
        {
            "id": "docprocessing",
            "label": "Document Processing",
            "fields": [
                {
                    "field": "workitem_id",
                    "label": "Workitem ID",
                    "type": "string",
                    "filterable": True,
                    "sortable": True,
                }
            ],
            "processes": [],
            "metrics": [
                {
                    "code": "workitem_count",
                    "label": "Workitem count (distinct)",
                    "aggregation": "count_distinct",
                    "base_field": "workitem_id",
                }
            ],
        }
    ]
    text, _ = ai_schema.serialize_sources_catalog(sources)
    assert "workitem_count" in text
    assert "metrics: none" not in text


def test_partial_tables_block_marks_per_process_tables_and_names_the_union_source():
    text = ai_schema.serialize_partial_tables(
        {
            "dbo.Compass_Invoice": {
                "processes": ["privera.03_Invoice_New"],
                "import_col": "ImportDate",
                "export_col": "ExportDate",
            },
            "dbo.BFH_Statistic": {"processes": ["bfh.01_Mail"]},
        },
        "docprocessing",
    )
    assert "dbo.Compass_Invoice = process privera.03_Invoice_New" in text
    # the per-table date columns: without them the UNION the prompt demands
    # fails on "Invalid column name" instead of on coverage
    assert "export date: ExportDate" in text
    assert "dbo.BFH_Statistic = process bfh.01_Mail" in text
    # the two rules the agent kept breaking (issue #128)
    assert "docprocessing" in text
    assert "NOT evidence of zero" in text


def test_partial_tables_block_is_empty_when_statconfig_yields_nothing():
    assert ai_schema.serialize_partial_tables({}, "docprocessing") == ""
    assert ai_schema.serialize_partial_tables(None, "docprocessing") == ""


def test_serialize_schema_puts_the_partial_warning_before_the_table_dump():
    conn = _FakeConn(_rows(("dbo", "Compass_Invoice", "Id", "int")))
    text, _ = ai_schema.serialize_schema(
        targets={"statistics": (lambda: conn)},
        curated=[],
        partial_tables={"dbo.Compass_Invoice": {"processes": ["privera.03_Invoice_New"]}},
    )
    assert text.index("PARTIAL") < text.index("# Target: statistics")


def test_serialize_schema_without_partial_tables_is_unchanged():
    conn = _FakeConn(_rows(("dbo", "Workitems", "Id", "int")))
    text, _ = ai_schema.serialize_schema(targets={"statistics": (lambda: conn)}, curated=[])
    assert text.startswith("# Target: statistics")


def test_partial_tables_block_declares_unregistered_tables_out_of_universe():
    # dbo.BFH_Statistic / dbo.DPSLicenseCounter exist in the statistics DB but are
    # not in Statconfig — the agent answered company-wide questions from them (#128).
    text = ai_schema.serialize_partial_tables(
        {"dbo.Compass_Invoice": {"processes": ["compass.01_Invoice_SAP"]}}, "docprocessing"
    )
    assert "COMPLETE" in text
    assert "NOT part of source docprocessing" in text
