"""Migration 0097 wires a reporting source's column catalog to its measures by
name, in SQL, with no type checker in between: a metric whose BaseField is not
in ColumnsJSON produces `AVG([Typo])` and a 500 at run time, not an error at
migration time. These checks read the migration text and catch that on commit.

Pure text/JSON parsing — no DB, no sqlcmd.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "sql" / "_migrations" / "NexoraDB" / "0097_em_field_extraction_quality.sql"


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def catalog(sql):
    """The source's ColumnsJSON, as the reporting layer will parse it."""
    match = re.search(r"N'(\[\{\"field\".*?\}\])'", sql, re.DOTALL)
    assert match, "ColumnsJSON literal not found in the migration"
    return json.loads(match.group(1))


def test_columns_json_is_valid_and_complete(catalog):
    fields = {c["field"] for c in catalog}
    # The grain columns the "over time" breakdown needs.
    assert {"ImportDate", "ExportDate"} <= fields
    assert all(c.get("grainable") for c in catalog if c["field"].endswith("Date"))
    # The dimension the whole source exists to rank.
    assert {"Field", "FieldLabel", "FieldKey"} <= fields


def test_every_metric_base_field_exists_in_the_catalog(sql, catalog):
    fields = {c["field"] for c in catalog}
    # ('code', 'source', ..., 'agg', 'BaseField'|NULL, ...) tuples in the VALUES list.
    bases = re.findall(r"'(count|count_distinct|sum|avg|min|max)',\s*(NULL|'(\w+)')", sql)
    assert bases, "no metric rows parsed out of the migration"
    for aggregation, raw, base in bases:
        if raw == "NULL":
            assert aggregation == "count", f"{aggregation} needs a base field"
            continue
        assert base in fields, f"metric base field {base!r} is not in ColumnsJSON"


def test_rate_columns_are_float_not_int(sql):
    # 0/100 floats, not 0/1 ints: the reporting layer emits a bare AVG(col) and
    # T-SQL integer-divides AVG over an int column, so every rate would come
    # back 0 or 1. `100e0` is what keeps them float.
    view = sql.split("CREATE OR ALTER VIEW", 1)[1].split("GO", 1)[0]
    for line in view.splitlines():
        if "Pct," in line or "Pct\n" in line:
            continue
        assert " THEN 100 " not in line, f"integer literal in a rate column: {line.strip()}"
    assert "100e0" in view


def test_no_hardcoded_statistics_database_name(sql):
    # The statistics DB is named differently per environment; hardcoding INT's
    # name ships a view that is broken on PROD.
    assert "$(StatisticsDb)" in sql
    for name in ("SYDOC_Statistik].", "sydoc_stat].", "sydoc_stat_INT]."):
        assert name not in sql, f"hardcoded database name {name!r}"


def test_no_raw_document_values_are_exposed(catalog):
    # Field *values* are customer document content and stay out of reporting.
    fields = {c["field"].lower() for c in catalog}
    for leaked in (
        "value_before_validation",
        "value_after_validation",
        "valuebefore",
        "valueafter",
    ):
        assert leaked not in fields
