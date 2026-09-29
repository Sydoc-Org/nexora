"""The Sydoc Finance spec matches the registered sources and builds the right SQL (#408).

nx_lib/finance.py is pure: the registry rows come in from the view. Here they
come from the migrations that seeded them (0126-0137), parsed the way
test_billing_sources.py reads them, so a section that names a field or a
measure the source does not carry fails here -- long before the page shows a
grand total where a breakdown should be.
"""

import datetime as dt
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from nx_lib import finance
from nx_lib.finance import (
    SECTIONS,
    SECTIONS_BY_KEY,
    FinanceSpecError,
    assemble_section,
    build_section_queries,
    export_rows,
    month_options,
    parse_month,
    shift_month,
)
from nx_lib.reporting.table_query import table_source_catalog

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "sql" / "_migrations" / "NexoraDB"

_SOURCE_RE = re.compile(
    r"'([a-z0-9_]+)',\s*'curated',\s*N'[^']*',\s*'reporting\.source\.[a-z0-9_]+\.use',"
    r"\s*'statistics',\s*'table',\s*'([^']+)',\s*N'(\[\{\"field\".*?\])'",
    re.S,
)
_METRIC_RE = re.compile(
    r"\('([a-z0-9_]+)',\s*'([a-z0-9_]+)',"
    r"(?:\s*N'(?:[^']|'')*',){4}"
    r"\s*'([a-z_]+)',\s*(NULL|'[A-Za-z0-9_]+'),\s*(?:(NULL|N'\[.*?\]'),\s*)?N'",
    re.S,
)
_REPOINT_RE = re.compile(r"SET BaseObject = '([^']+)',\s*ColumnsJSON = N'(\[.*?\])'", re.S)
_REBASE_RE = re.compile(r"\('([a-z0-9_]+)',\s*'([A-Za-z0-9_]+)'\)")


def _registry():
    """{source code: (base_object, catalog, source_metrics)} as the migrations seeded them."""
    sources, metrics = {}, {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        for code, base_object, columns in _SOURCE_RE.findall(sql):
            sources[code] = (base_object, json.loads(columns))
        if "INSERT INTO dbo.ReportingMetrics" in sql:
            for code, source, agg, base, filt in _METRIC_RE.findall(sql):
                metrics[code] = {
                    "source": source,
                    "aggregation": agg,
                    "base_field": None if base == "NULL" else base.strip("'"),
                    "filter": json.loads(filt[2:-1]) if filt and filt != "NULL" else None,
                    "label": code,
                }
        if path.name.startswith("0137_"):
            m = _REPOINT_RE.search(sql)
            assert m, "0137 no longer repoints the frigemo source"
            sources["frigemo"] = (m.group(1), json.loads(m.group(2)))
            for code, base in _REBASE_RE.findall(sql.split("JOIN (VALUES", 1)[1]):
                metrics[code]["base_field"] = base
    out = {}
    for code, (base_object, columns) in sources.items():
        source_metrics = {c: m for c, m in metrics.items() if m["source"] == code}
        out[code] = (base_object, table_source_catalog(columns), source_metrics)
    return out


REGISTRY = _registry()


def _queries(key, year=2026, month=9):
    section = SECTIONS_BY_KEY[key]
    base_object, catalog, source_metrics = REGISTRY[section.source]
    return build_section_queries(section, base_object, catalog, source_metrics, year, month)


# --------------------------------------------------------------------------
# The month
# --------------------------------------------------------------------------


def test_parse_month_defaults_to_the_previous_month():
    """Accounting invoices the month that just closed, not the one running."""
    assert parse_month(None, dt.date(2026, 9, 29)) == (2026, 8)
    assert parse_month("", dt.date(2026, 1, 5)) == (2025, 12)


@pytest.mark.parametrize("garbage", ["2026", "2026-00", "2026-13", "x-y", "2026-9-1", "09/2026"])
def test_parse_month_falls_back_on_garbage(garbage):
    assert parse_month(garbage, dt.date(2026, 9, 29)) == (2026, 8)


def test_parse_month_clamps_to_the_current_month_and_the_earliest_year():
    today = dt.date(2026, 9, 29)
    assert parse_month("2027-03", today) == (2026, 9)
    assert parse_month("2026-09", today) == (2026, 9)
    assert parse_month("1999-12", today) == (finance.EARLIEST_YEAR, 1)
    assert parse_month("2024-02", today) == (2024, 2)


def test_month_options_run_newest_first_from_the_current_month():
    opts = month_options(dt.date(2026, 9, 29), count=3)
    assert opts == [("2026-09", 2026, 9), ("2026-08", 2026, 8), ("2026-07", 2026, 7)]


def test_shift_month_crosses_years():
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2025, 12, 1) == (2026, 1)
    assert shift_month(2026, 9, -24) == (2024, 9)


# --------------------------------------------------------------------------
# The spec against the registry
# --------------------------------------------------------------------------


def test_section_keys_are_unique_and_url_safe():
    keys = [s.key for s in SECTIONS]
    assert len(keys) == len(set(keys))
    assert all(re.fullmatch(r"[a-z0-9_]+", k) for k in keys)


@pytest.mark.parametrize("section", SECTIONS, ids=[s.key for s in SECTIONS])
def test_every_section_matches_its_registered_source(section):
    """Every field and measure a section names exists on the source the
    migrations registered, and belongs to it -- the whole point of reading the
    registry instead of hand-writing SQL is that this cannot drift."""
    assert section.source in REGISTRY, f"{section.key}: source {section.source!r} is not seeded"
    _, catalog, source_metrics = REGISTRY[section.source]
    fields = {f["field"] for f in catalog}
    for block in section.blocks:
        for f in block.period.fields():
            assert f in fields, f"{section.key}: period field {f!r} not in catalog"
        for code in block.figures:
            assert (
                code in source_metrics
            ), f"{section.key}: measure {code!r} not on {section.source}"
        for br in block.breakdowns:
            assert br.dim in fields, f"{section.key}: dimension {br.dim!r} not in catalog"
            assert set(br.metrics) <= set(block.figures)


@pytest.mark.parametrize("section", SECTIONS, ids=[s.key for s in SECTIONS])
def test_every_section_builds_its_queries(section):
    queries = _queries(section.key)
    kinds = [(q.block, q.kind) for q in queries]
    for i, block in enumerate(section.blocks):
        assert (i, "figures") in kinds and (i, "previous") in kinds
        assert sum(1 for q in queries if q.block == i and q.kind == "breakdown") == len(
            block.breakdowns
        )
    for q in queries:
        assert q.sql.startswith("SELECT TOP (")
        assert "?" * q.sql.count("?") == "?" * len(q.params)


# --------------------------------------------------------------------------
# The month, per source -- the load-bearing differences of #329
# --------------------------------------------------------------------------


def _first(key, kind, dim=None):
    return next(q for q in _queries(key) if q.kind == kind and q.dim == dim)


def test_elektro_material_selects_the_month_on_the_real_export_datetime():
    """ExportEM_dt, never the nvarchar ExportEM; a half-open range, bound as
    ISO strings -- the legacy ODBC driver refuses a Python date (HYC00)."""
    q = _first("elektro_material", "figures")
    assert "[ExportEM_dt] >= ? AND [ExportEM_dt] < ?" in q.sql
    assert "ExportEM]" not in q.sql
    assert q.params[-2:] == ["2026-09-01", "2026-10-01"]


def test_elektro_material_measures_keep_their_channel_filter():
    """The 0130 rule: only Opex + e-mail are billed, as conditional aggregates."""
    q = _first("elektro_material", "figures")
    assert q.sql.count("CASE WHEN [Eingang] IN (?,?)") == 3
    assert q.params[:6] == ["OPEX Scan Scanner", "E_MAIL"] * 3


def test_compass_bills_on_the_upload_date_not_the_document_date():
    q = _first("compass", "figures")
    assert "[UploadDatetime] >= ?" in q.sql
    assert "DocDate" not in q.sql
    assert "COUNT(*) AS [compass_documents]" in q.sql


def test_posteingang_matches_the_month_inside_the_text_date():
    """The 0135 rule: ExportDatetime is text, so the month is a contains filter."""
    q = _first("privera_posteingang", "figures")
    assert "[ExportDatetime] LIKE ?" in q.sql
    assert q.params == ["%.09.2026%"]
    assert "CAST" not in q.sql and "DATEFROMPARTS" not in q.sql


def test_neuzugaenge_selects_the_year_and_month_columns():
    """The 0134 view is pre-aggregated: a year and a month number, no date."""
    q = _first("privera_neuzugaenge", "figures")
    assert "[JahrExport] = ? AND [MonatExportNr] = ?" in q.sql
    assert q.params == [2026, 9]
    assert "SUM([AnzahlDossiersExport]) AS [privera_neuzugaenge_dossiers]" in q.sql


def test_previous_month_query_is_the_month_before():
    q = _first("privera_invoice", "previous")
    assert q.params[-2:] == ["2026-08-01", "2026-09-01"]
    p = _first("privera_posteingang", "previous")
    assert p.params == ["%.08.2026%"]
    n = _first("privera_neuzugaenge", "previous")
    assert n.params == [2026, 8]


def test_january_previous_month_is_december_of_the_year_before():
    section = SECTIONS_BY_KEY["compass"]
    base_object, catalog, metrics = REGISTRY[section.source]
    queries = build_section_queries(section, base_object, catalog, metrics, 2026, 1)
    prev = next(q for q in queries if q.kind == "previous")
    assert prev.params[-2:] == ["2025-12-01", "2026-01-01"]


def test_bucherer_uses_a_different_month_basis_per_block():
    """Imported documents and pages follow ImportTime, exported ones ExportTime."""
    queries = _queries("bucherer")
    imported = next(q for q in queries if q.block == 0 and q.kind == "figures")
    exported = next(q for q in queries if q.block == 1 and q.kind == "figures")
    assert (
        "[ImportTime] >= ?" in imported.sql and "ExportTime" not in imported.sql.split("WHERE")[1]
    )
    assert "[ExportTime] >= ?" in exported.sql


def test_breakdown_groups_by_the_dimension_and_sorts_by_the_lead_measure():
    q = _first("privera_invoice", "breakdown", "Mandant")
    assert q.sql.startswith("SELECT TOP (1000) [Mandant], COUNT(*) AS [privera_documents]")
    assert q.sql.endswith("GROUP BY [Mandant] ORDER BY [privera_documents] DESC")
    assert q.metrics == ("privera_documents", "privera_mail_documents", "privera_ebill_documents")


def test_breakdown_can_narrow_its_columns():
    """DocSource only shows the total: mail and eBill are DocSource values themselves."""
    q = _first("privera_invoice", "breakdown", "DocSource")
    assert q.metrics == ("privera_documents",)
    assert "privera_mail_documents" not in q.sql


def test_xpert_breaks_documents_down_per_client_and_source_database():
    dims = {q.dim for q in _queries("xpert") if q.kind == "breakdown"}
    assert dims == {"Client", "SourceDb"}
    q = _first("xpert", "breakdown", "Client")
    assert "SUM(CASE WHEN [Metric] = ? THEN [Cnt] END) AS [xpert_stats_documents]" in q.sql
    assert q.params[0] == "Total"


def test_bps_service_hours_exclude_absences_and_break_down_per_task_and_customer():
    """The timetool overview: hours on real work, per BPS task and per customer,
    with absences counted separately -- the 0138 measure, inverted 0124."""
    q = _first("bps", "figures")
    assert "SUM(CASE WHEN [Kunde] <> ? THEN [Stunden] END) AS [bps_projects_service_hours]" in q.sql
    assert "SUM(CASE WHEN [Kunde] = ? THEN [Stunden] END) AS [bps_projects_absence_hours]" in q.sql
    assert q.params[:2] == ["Absences", "Absences"]
    assert "[Datum] >= ? AND [Datum] < ?" in q.sql
    dims = {q.dim: q.metrics for q in _queries("bps") if q.kind == "breakdown"}
    assert dims == {
        "Aufgabe": ("bps_projects_service_hours",),
        "Kunde": ("bps_projects_service_hours",),
    }
    assert SECTIONS_BY_KEY["bps"].group == finance.SERVICES


def test_hours_keep_their_fraction_and_totals_do_not_carry_float_noise():
    section = SECTIONS_BY_KEY["bps"]
    queries = _queries("bps")
    rows = _rows_for(
        queries,
        figures=(Decimal("655.8011"), Decimal("1146.9332"), Decimal("1802.7343")),
        previous=(Decimal("700"), Decimal("0"), Decimal("700")),
        breakdown=[
            ("Validierung", Decimal("0.1")),
            ("Support", Decimal("0.2")),
            ("Absences", None),
        ],
    )
    payload = assemble_section(
        section, queries, rows, source_label=None, metric_label=str, translate=str
    )
    figures = payload["blocks"][0]["figures"]
    assert figures[0]["value"] == 655.8011 and figures[0]["prev"] == 700
    br = payload["blocks"][0]["breakdowns"][0]
    assert br["rows"] == [
        {"key": "Validierung", "values": [0.1]},
        {"key": "Support", "values": [0.2]},
    ]
    assert br["totals"] == [0.3]


def test_a_dimension_missing_from_the_catalog_fails_loudly():
    """build_generic_query silently drops an unknown column and returns a grand
    total in its place -- a breakdown that quietly became one number would be
    the worst failure for an accounting page, so the spec check must raise."""
    section = SECTIONS_BY_KEY["mediamarkt"]
    base_object, catalog, metrics = REGISTRY[section.source]
    trimmed = [c for c in catalog if c["field"] != "DocType"]
    with pytest.raises(FinanceSpecError, match="DocType"):
        build_section_queries(section, base_object, trimmed, metrics, 2026, 9)


def test_a_missing_period_field_fails_loudly():
    section = SECTIONS_BY_KEY["privera_neuzugaenge"]
    base_object, catalog, metrics = REGISTRY[section.source]
    trimmed = [c for c in catalog if c["field"] != "MonatExportNr"]
    with pytest.raises(FinanceSpecError, match="MonatExportNr"):
        build_section_queries(section, base_object, trimmed, metrics, 2026, 9)


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------


def _rows_for(queries, figures, previous, breakdown):
    out = []
    for q in queries:
        if q.kind == "figures":
            out.append([figures])
        elif q.kind == "previous":
            out.append([previous])
        else:
            out.append(breakdown)
    return out


def test_assemble_section_folds_rows_into_figures_and_breakdowns():
    section = SECTIONS_BY_KEY["privera_nachsendungen"]
    queries = _queries("privera_nachsendungen")
    rows = _rows_for(
        queries,
        figures=(Decimal("1667"), 1042),
        previous=(1500, None),
        breakdown=[("Zürich", 900, 600), ("TEC", 610, 0), ("Leer", 0, None), (None, 157, 442)],
    )
    payload = assemble_section(
        section,
        queries,
        rows,
        source_label="Privera — Physische Zustellung",
        metric_label=lambda c: c.upper(),
        translate=lambda s: f"t:{s}",
    )
    assert payload["key"] == "privera_nachsendungen"
    assert payload["error"] is None
    assert payload["source"] == {
        "code": "privera_nachsendungen",
        "label": "Privera — Physische Zustellung",
    }
    block = payload["blocks"][0]
    assert block["basis"] == "t:by export date"
    assert block["figures"] == [
        {
            "code": "privera_nachsendungen_total",
            "label": "PRIVERA_NACHSENDUNGEN_TOTAL",
            "value": 1667,
            "prev": 1500,
        },
        {
            "code": "privera_nachsendungen_ohne_tec",
            "label": "PRIVERA_NACHSENDUNGEN_OHNE_TEC",
            "value": 1042,
            "prev": 0,
        },
    ]
    br = block["breakdowns"][0]
    assert br["dim"] == "Niederlassung" and br["label"] == "t:Branch"
    assert [c["code"] for c in br["columns"]] == list(queries[-1].metrics)
    # The all-zero group is dropped, NULL becomes a None key, Decimal a plain int.
    assert br["rows"] == [
        {"key": "Zürich", "values": [900, 600]},
        {"key": "TEC", "values": [610, 0]},
        {"key": None, "values": [157, 442]},
    ]
    assert br["totals"] == [1667, 1042]
    assert isinstance(block["figures"][0]["value"], int)


def test_assemble_section_with_no_rows_is_all_zeros_not_an_error():
    section = SECTIONS_BY_KEY["compass"]
    queries = _queries("compass")
    payload = assemble_section(
        section,
        queries,
        [[] for _ in queries],
        source_label=None,
        metric_label=lambda c: c,
        translate=lambda s: s,
    )
    assert payload["blocks"][0]["figures"] == [
        {"code": "compass_documents", "label": "compass_documents", "value": 0, "prev": 0}
    ]
    assert payload["note"] is not None


def test_assemble_section_refuses_misaligned_rows():
    section = SECTIONS_BY_KEY["compass"]
    queries = _queries("compass")
    with pytest.raises(ValueError):
        assemble_section(section, queries, [[]], source_label=None, metric_label=str, translate=str)


def test_export_rows_flatten_figures_and_breakdown_cells():
    payload = {
        "client": "Privera",
        "title": "Rechnungseingang",
        "error": None,
        "blocks": [
            {
                "basis": "by export date",
                "figures": [{"code": "a", "label": "Documents", "value": 10, "prev": 8}],
                "breakdowns": [
                    {
                        "dim": "Mandant",
                        "label": "Mandant",
                        "columns": [{"code": "a", "label": "Documents"}],
                        "rows": [{"key": "M1", "values": [7]}, {"key": None, "values": [3]}],
                        "totals": [10],
                    }
                ],
            }
        ],
    }
    rows = export_rows(payload)
    assert rows == [
        ["Privera", "Rechnungseingang", "by export date", "figure", "", "", "Documents", 10, 8],
        [
            "Privera",
            "Rechnungseingang",
            "by export date",
            "breakdown",
            "Mandant",
            "M1",
            "Documents",
            7,
            "",
        ],
        [
            "Privera",
            "Rechnungseingang",
            "by export date",
            "breakdown",
            "Mandant",
            "",
            "Documents",
            3,
            "",
        ],
    ]


def test_export_rows_carry_a_failed_section_as_one_line():
    rows = export_rows({"client": "Privera", "title": "Neuzugänge", "error": "boom", "blocks": []})
    assert rows == [["Privera", "Neuzugänge", "", "error", "", "", "boom", "", ""]]
