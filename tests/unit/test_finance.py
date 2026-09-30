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

from nx_lib import bps, finance
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
_APPEND_COL_RE = re.compile(
    r"JSON_QUERY\(N'(\{\"field\".*?\})'\)\)\s*WHERE Code = '([a-z0-9_]+)'", re.S
)
_REFILTER_RE = re.compile(
    r"UPDATE dbo\.ReportingMetrics\s+SET FilterJson = N'(\[.*?\])',.*?WHERE Code = '([a-z0-9_]+)'",
    re.S,
)


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
        if path.name.startswith("0139_"):
            appended = _APPEND_COL_RE.findall(sql)
            refiltered = _REFILTER_RE.findall(sql)
            assert appended and refiltered, "0139 no longer patches the registry"
            for column, code in appended:
                sources[code][1].append(json.loads(column))
            for filt, code in refiltered:
                metrics[code]["filter"] = json.loads(filt)
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
        n = sum(1 for q in queries if q.block == i and q.kind in ("breakdown", "matrix"))
        assert n == len(block.breakdowns)
    if section.bookings:
        rules = len(section.bookings.rules)
        assert sum(1 for q in queries if q.kind == "bookings") == rules
        assert sum(1 for q in queries if q.kind.startswith("bookings_")) == 2 * rules
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


def test_privera_mail_follows_the_workbooks_file_name_rule():
    """0139: the Mail pivot drops MAIL rows without a file name; so does the measure."""
    q = _first("privera_invoice", "figures")
    mail = next(part for part in q.sql.split(", ") if "[privera_mail_documents]" in part)
    assert "[DocSource] = ?" in mail and "[FileName] IS NOT NULL" in mail


def test_mediamarkt_batches_skip_placeholder_rows():
    """0139: a pre-typed batch number without pieces is not a batch."""
    q = _first("mediamarkt", "figures")
    batches = next(part for part in q.sql.split(", ") if "[mediamarkt_batches]" in part)
    assert "[Pieces] IS NOT NULL" in batches


def test_privera_matrices_pivot_register_and_forwarding_type_by_branch():
    """The billed "PRIVERA" sheets: one measure, rows down, branches along."""
    post = _first("privera_posteingang", "matrix", "Register")
    assert post.sql.startswith("SELECT TOP (1000) [Register], [Niederlassung], COUNT(*)")
    assert "GROUP BY [Register], [Niederlassung]" in post.sql
    zust = _first("privera_nachsendungen", "matrix", "Nachsendungstyp")
    assert zust.metrics == ("privera_nachsendungen_total",)
    assert "GROUP BY [Nachsendungstyp], [Niederlassung]" in zust.sql


def test_bps_lists_billable_bookings_one_query_per_rule():
    """The generic grammar only ANDs: each billable rule is its own row query,
    plus an aggregate for this and the previous month."""
    queries = _queries("bps")
    rows = [q for q in queries if q.kind == "bookings"]
    assert len(rows) == 2
    assert rows[0].sql.startswith(
        "SELECT TOP (5000) [Datum], [Kunde], [Projektpaket], [Aufgabe], [Benutzer], [Stunden],"
    )
    assert "[Aufgabe] IN (?,?,?,?,?,?) AND [Kunde] NOT IN (?,?)" in rows[0].sql
    assert rows[0].params[:2] == ["2026-09-01", "2026-10-01"]
    assert rows[0].params[2:] == [*bps.BILLABLE_TASKS, *bps.INTERNAL_CUSTOMERS]
    assert "[Aufgabe] = ? AND [Kunde] = ? AND [Projektpaket] = ?" in rows[1].sql
    assert rows[1].params[2:] == list(bps.PREPARATION)
    prev = next(q for q in queries if q.kind == "bookings_previous" and q.block == 1)
    assert prev.params[:2] == ["2026-08-01", "2026-09-01"]
    assert "SUM([Stunden])" in prev.sql and "COUNT(*)" in prev.sql
    assert SECTIONS_BY_KEY["bps"].group == finance.SERVICES


def test_bps_bookings_merge_group_per_customer_and_total_from_the_aggregates():
    section = SECTIONS_BY_KEY["bps"]
    queries = _queries("bps")
    day = dt.date(2026, 8, 4)
    by_kind = {
        (0, "bookings"): [
            [
                day,
                "ISS",
                "Hypotheken",
                "Change",
                "Anna  Muster",
                Decimal("1.3333"),
                "CR &amp; Test ",
            ],
            [day, "Bucherer", "EasyTax", "Change", "Ben Beispiel", Decimal("0.75"), "ITHD-3805"],
        ],
        (1, "bookings"): [
            [
                day,
                "Privera",
                "Tagesgeschäft Neuzugänge",
                "Vorbereitung Akten",
                "Cem",
                Decimal("2"),
                "x",
            ]
        ],
        (0, "bookings_figures"): [[Decimal("2.0833"), 2]],
        (1, "bookings_figures"): [[Decimal("2"), 1]],
        (0, "bookings_previous"): [[Decimal("5"), 4]],
        (1, "bookings_previous"): [[None, 0]],
    }
    rows = [by_kind.get((q.block, q.kind), []) for q in queries]
    payload = assemble_section(
        section, queries, rows, source_label=None, metric_label=str, translate=str
    )
    bk = payload["bookings"]
    assert payload["blocks"] == []
    assert [f["value"] for f in bk["figures"]] == [4.0833, 3]
    assert [f["prev"] for f in bk["figures"]] == [5, 4]
    assert [g["key"] for g in bk["groups"]] == ["Bucherer", "ISS", "Privera"]
    iss = bk["groups"][1]
    assert iss["hours"] == 1.3333 and iss["count"] == 1
    # Entities decoded, blanks trimmed, the doubled blank in a name collapsed.
    assert iss["rows"][0] == [
        "2026-08-04",
        "ISS",
        "Hypotheken",
        "Change",
        "Anna Muster",
        1.3333,
        "CR & Test",
    ]
    assert {t["key"]: t["hours"] for t in bk["by_task"]} == {
        "Change": 2.0833,
        "Vorbereitung Akten": 2,
    }
    assert bk["truncated"] is False


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


def _rows_for(queries, figures, previous, breakdown, matrix=()):
    out = []
    for q in queries:
        if q.kind == "figures":
            out.append([figures])
        elif q.kind == "previous":
            out.append([previous])
        elif q.kind == "matrix":
            out.append(list(matrix))
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
        matrix=[
            ("Inkasso", "Zürich", 500),
            ("Depot", "Zürich", 400),
            ("Inkasso", "TEC", 3),
            (None, "Bern", 0),
        ],
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
    branch_q = next(q for q in queries if q.kind == "breakdown")
    assert [c["code"] for c in br["columns"]] == list(branch_q.metrics)
    # The all-zero group is dropped, NULL becomes a None key, Decimal a plain int.
    assert br["rows"] == [
        {"key": "Zürich", "values": [900, 600]},
        {"key": "TEC", "values": [610, 0]},
        {"key": None, "values": [157, 442]},
    ]
    assert br["totals"] == [1667, 1042]
    assert isinstance(block["figures"][0]["value"], int)
    # The matrix: alphabetical like the workbook pivots, zero cells and all-zero keys dropped.
    mx = block["breakdowns"][1]
    assert mx["kind"] == "matrix" and mx["label"] == "t:Forwarding type"
    assert mx["across_label"] == "t:Branch"
    assert mx["row_keys"] == ["Depot", "Inkasso"] and mx["col_keys"] == ["TEC", "Zürich"]
    assert mx["cells"] == [[0, 400], [3, 500]]
    assert mx["row_totals"] == [400, 503] and mx["col_totals"] == [3, 900]
    assert mx["total"] == 903


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
        ["Privera", "Rechnungseingang", "by export date", "figure", "", "", "Documents", 10, 8, ""],
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
            "",
        ],
    ]


def test_export_rows_carry_a_failed_section_as_one_line():
    rows = export_rows({"client": "Privera", "title": "Neuzugänge", "error": "boom", "blocks": []})
    assert rows == [["Privera", "Neuzugänge", "", "error", "", "", "boom", "", "", ""]]


def test_export_rows_list_every_booking_with_its_detail():
    payload = {
        "client": "Sydoc",
        "title": "Billable services",
        "error": None,
        "blocks": [],
        "bookings": {
            "basis": "by booking date",
            "figures": [
                {"code": "billable_hours", "label": "Billable hours", "value": 1.5, "prev": 2}
            ],
            "columns": [{"field": f, "label": f} for f in bps.BOOKING_COLUMNS],
            "group_by": "Kunde",
            "groups": [
                {
                    "key": "ISS",
                    "hours": 1.5,
                    "count": 1,
                    "rows": [["2026-08-04", "ISS", "Hypotheken", "Change", "Anna", 1.5, "CR"]],
                }
            ],
        },
    }
    rows = export_rows(payload)
    assert rows[0][3:9] == ["figure", "", "", "Billable hours", 1.5, 2]
    assert rows[1] == [
        "Sydoc",
        "Billable services",
        "by booking date",
        "booking",
        "Kunde",
        "ISS",
        "Change",
        1.5,
        "",
        "2026-08-04 · Hypotheken · Anna · CR",
    ]


# --------------------------------------------------------------------------
# Month close
# --------------------------------------------------------------------------


def _fig(code, label, value):
    return {"code": code, "label": label, "value": value}


def test_diff_payload_reports_only_figures_that_moved():
    closed = {
        "blocks": [{"figures": [_fig("a", "Docs", 12188), _fig("b", "Img", 5)]}],
        "bookings": {"figures": [_fig("billable_hours", "Hours", 3)]},
    }
    live = {
        "blocks": [{"figures": [_fig("a", "Docs", 12186), _fig("b", "Img", 5)]}],
        "bookings": {"figures": [_fig("billable_hours", "Hours", 3)]},
    }
    assert finance.diff_payload(closed, live) == [{"label": "Docs", "closed": 12188, "live": 12186}]
    assert finance.diff_payload(closed, closed) == []


def test_diff_payload_counts_a_figure_missing_on_one_side_as_zero():
    closed = {"blocks": [{"figures": [_fig("a", "Docs", 4)]}]}
    live = {"blocks": [{"figures": [_fig("z", "New", 1)]}]}
    assert finance.diff_payload(closed, live) == [
        {"label": "Docs", "closed": 4, "live": 0},
        {"label": "New", "closed": 0, "live": 1},
    ]
