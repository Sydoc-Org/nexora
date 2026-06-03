"""Unit tests for AI schema serialization (DB injected as a fake cursor)."""

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


def _rows(*triples):
    # (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE)
    return [
        type("R", (), dict(TABLE_SCHEMA=s, TABLE_NAME=t, COLUMN_NAME=c, DATA_TYPE=d))()
        for (s, t, c, d) in triples
    ]


def test_serialize_target_groups_columns_by_table():
    cur = _FakeCursor(
        _rows(
            ("dbo", "Workitems", "Id", "int"),
            ("dbo", "Workitems", "Status", "nvarchar"),
            ("dbo", "Users", "UserId", "int"),
        )
    )
    text = ai_schema.serialize_target("statistics", lambda: cur)
    assert "dbo.Workitems" in text and "Id int" in text and "Status nvarchar" in text
    assert "dbo.Users" in text and "UserId int" in text


def test_serialize_schema_respects_char_budget_and_logs(monkeypatch, caplog):
    cur = _FakeCursor(_rows(*[("dbo", f"T{i}", "C", "int") for i in range(200)]))
    text, truncated = ai_schema.serialize_schema(
        targets={"statistics": (lambda: cur)},
        curated=[],
        char_budget=200,
    )
    assert len(text) <= 400  # budget + a small truncation marker
    assert truncated is True
    assert "truncated" in text.lower()


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
