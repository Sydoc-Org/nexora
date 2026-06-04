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
