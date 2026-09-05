"""The field-quality migrations wire a reporting source's column catalog to its
measures by name, in SQL, with no type checker in between: a metric whose
BaseField is not in ColumnsJSON produces `AVG([Typo])` and a 500 at run time,
not an error at migration time. These checks read the migration text and catch
that on commit.

Pure text/JSON parsing — no DB, no sqlcmd.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "sql" / "_migrations" / "NexoraDB"
# 0097 created the source and its measures; 0100 unioned it across all seven
# clients and owns the current catalog. Both stay in scope: the measures live in
# one file and the columns they aggregate in the other.
CREATE = MIGRATIONS / "0097_em_field_extraction_quality.sql"
UNION = MIGRATIONS / "0100_field_quality_all_clients.sql"

# Every telemetry table in the statistics DB. Adding a client means adding a
# UNION ALL block; this list is what makes forgetting one a test failure.
CLIENT_TABLES = [
    "Bucherer_Collect_Field_Attributes",
    "Compass_Collect_Field_Attributes",
    "Em_Collect_Field_Attributes",
    "Geberit_Collect_Field_Attributes",
    "PriveraInvoice_Collect_Field_Attributes",
    "PriveraInvoice2025_Collect_Field_Attributes",
    "PriveraPost_Collect_Field_Attributes",
]


def _catalog(sql: str) -> list[dict]:
    match = re.search(r"N'(\[\{\"field\".*?\}\])'", sql, re.DOTALL)
    assert match, "ColumnsJSON literal not found in the migration"
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def create_sql():
    return CREATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def union_sql():
    return UNION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def catalog(union_sql):
    """The source's live ColumnsJSON, as the reporting layer will parse it."""
    return _catalog(union_sql)


def test_columns_json_is_valid_and_complete(catalog):
    fields = {c["field"] for c in catalog}
    # The grain columns the "over time" breakdown needs.
    assert {"ImportDate", "ExportDate"} <= fields
    assert all(c.get("grainable") for c in catalog if c["field"].endswith("Date"))
    # The dimension the whole source exists to rank, and the two that slice it.
    assert {"Field", "FieldLabel", "FieldKey", "Customer", "Stream"} <= fields


def test_every_metric_base_field_exists_in_the_catalog(create_sql, catalog):
    fields = {c["field"] for c in catalog}
    # ('code', 'source', ..., 'agg', 'BaseField'|NULL, ...) tuples in the VALUES list.
    bases = re.findall(r"'(count|count_distinct|sum|avg|min|max)',\s*(NULL|'(\w+)')", create_sql)
    assert bases, "no metric rows parsed out of the migration"
    for aggregation, raw, base in bases:
        if raw == "NULL":
            assert aggregation == "count", f"{aggregation} needs a base field"
            continue
        assert base in fields, f"metric base field {base!r} is not in ColumnsJSON"


def test_union_kept_every_column_the_pilot_catalog_had(create_sql, catalog):
    # 0100 rewrote the catalog. Dropping a field silently breaks any saved report
    # that used it, so the union may only ever add.
    before = {c["field"] for c in _catalog(create_sql)}
    after = {c["field"] for c in catalog}
    assert before <= after, f"union dropped columns: {sorted(before - after)}"


def test_every_client_telemetry_table_is_unioned(union_sql):
    for table in CLIENT_TABLES:
        assert f"dbo.{table}" in union_sql, f"{table} is missing from the union"


def test_date_join_is_keyed_on_stream_not_customer(union_sql):
    # Privera has three telemetry tables across two header tables. Keying the
    # date join on Customer lets a workitem id present in both header tables
    # match twice and silently doubles those rows, inflating every average.
    view = union_sql.split("CREATE OR ALTER VIEW", 1)[1].split("\nGO", 1)[0]
    join = re.search(r"LEFT JOIN dates d\s*(.*?)\n(?=LEFT JOIN|--)", view, re.DOTALL)
    assert join, "the dates join was not found"
    assert "d.Stream" in join.group(1), "the dates join must be keyed on Stream"
    assert "Customer" not in join.group(1), "the dates join must not key on Customer"


def test_rate_columns_are_float_not_int(union_sql):
    # 0/100 floats, not 0/1 ints: the reporting layer emits a bare AVG(col) and
    # T-SQL integer-divides AVG over an int column, so every rate would come
    # back 0 or 1. `100e0` is what keeps them float.
    view = union_sql.split("CREATE OR ALTER VIEW", 1)[1].split("\nGO", 1)[0]
    for line in view.splitlines():
        if "Pct," in line or "Pct\n" in line:
            continue
        assert " THEN 100 " not in line, f"integer literal in a rate column: {line.strip()}"
    assert "100e0" in view


@pytest.mark.parametrize("path", [CREATE, UNION])
def test_no_hardcoded_statistics_database_name(path):
    # The statistics DB is named differently per environment; hardcoding INT's
    # name ships a view that is broken on PROD.
    sql = path.read_text(encoding="utf-8")
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


# --- 0101: onboarded processes only -----------------------------------------

ONBOARDED = MIGRATIONS / "0101_field_quality_onboarded_processes.sql"


@pytest.fixture(scope="module")
def onboarded_sql():
    return ONBOARDED.read_text(encoding="utf-8")


def test_process_filter_is_scoped_to_the_organization(onboarded_sql):
    # '02_Invoice' belongs to elektromaterial AND to privera. Matching on the
    # process name alone would let one customer's onboarding silently admit the
    # other's telemetry, so the EXISTS must also compare the organization.
    where = onboarded_sql.split("WHERE EXISTS", 1)[1].split(");", 1)[0]
    assert "dbo.ProcessSources" in where
    assert "OrganizationCode" in where, "the process filter must be org-scoped"
    assert "ClientCode" in where


def test_every_stream_declares_an_organization_slot(onboarded_sql):
    # Each UNION ALL branch carries an OrgCode -- a literal for an onboarded
    # customer, NULL for one with no dbo.Organizations row. A branch that
    # forgot it would not compile, but a branch that silently reused another
    # customer's code would cross-admit telemetry, so count them.
    view = onboarded_sql.split("CREATE OR ALTER VIEW", 1)[1].split("\nGO", 1)[0]
    cfa = view.split("WITH cfa AS", 1)[1].split("dates AS", 1)[0]
    assert cfa.count("AS OrgCode") == len(CLIENT_TABLES)


def test_onboarded_filter_keeps_the_catalog_and_view_in_step(onboarded_sql, catalog):
    # 0101 re-asserts 0100's ColumnsJSON. If the two ever diverge, a report
    # resolves a column the view no longer projects.
    assert [c["field"] for c in _catalog(onboarded_sql)] == [c["field"] for c in catalog]
