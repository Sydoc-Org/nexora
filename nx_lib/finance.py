"""Sydoc Finance -- the monthly accounting figures, one section per client (#408).

Pure and DB-free, in the spirit of nx_lib/reporting/semantic.py. This module
knows three things and nothing else:

* WHICH registered reporting sources and measures make up the monthly
  accounting report (``SECTIONS``) -- the six #329 billing workbooks, the
  external clients whose collectors already fill a Statistics table, and the
  hours Sydoc itself books in the BPS timetool (0124);
* HOW a calendar month selects rows in each of them (``Period``) -- a real
  date column is a half-open range, Posteingang's text date is a ``contains``
  on ``.MM.yyyy``, the pre-aggregated Neuzugaenge view is a year + month pair;
* how the aggregate rows come back out as the page's payload.

The registry rows (source descriptor, its metric registry, its field catalog)
are injected by the view, and the SQL is built by the very same builder the
Reporting page's 'table' provider uses (``build_generic_query`` over
``resolve_metrics``). So a figure on the Finance page and the same measure in
a report are one definition, not two that have to be kept in step -- see
docs/howto/finance.md.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from .reporting.semantic import resolve_metrics
from .reporting.table_query import build_generic_query

EARLIEST_YEAR = 2020
MONTH_OPTIONS = 36
BREAKDOWN_ROW_CAP = 1000

INTERNAL = "internal"
EXTERNAL = "external"
SERVICES = "services"


def N_(message):  # noqa: N802 -- pybabel's deferred-translation marker
    """Mark a msgid for extraction without translating it here.

    The section specs are module-level constants, evaluated at import time
    with no request (and so no locale) around; the view translates every
    marked string with gettext() when it renders.
    """
    return message


class FinanceSpecError(ValueError):
    """A section spec names something its registered source does not carry."""


# --------------------------------------------------------------------------
# The month
# --------------------------------------------------------------------------


def shift_month(year, month, delta):
    """(year, month) moved by `delta` months (negative = back)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_bounds(year, month):
    """[first day, first day of the next month) as dates."""
    ny, nm = shift_month(year, month, 1)
    return dt.date(year, month, 1), dt.date(ny, nm, 1)


def month_key(year, month):
    return f"{year:04d}-{month:02d}"


def parse_month(value, today=None):
    """``YYYY-MM`` from the query string -> (year, month), clamped and defaulted.

    The default is the *previous* calendar month: the one accounting is
    invoicing. The current month is the latest anyone may pick (it is still
    running), the earliest is January of ``EARLIEST_YEAR``. Anything
    unparseable falls back to the default rather than erroring -- the month is
    a navigation state, not user data.
    """
    today = today or dt.date.today()
    default = shift_month(today.year, today.month, -1)
    try:
        y_str, m_str = str(value or "").split("-", 1)
        year, month = int(y_str), int(m_str)
    except ValueError:
        return default
    if not 1 <= month <= 12:
        return default
    if (year, month) < (EARLIEST_YEAR, 1):
        return EARLIEST_YEAR, 1
    if (year, month) > (today.year, today.month):
        return today.year, today.month
    return year, month


def month_options(today=None, count=MONTH_OPTIONS):
    """The pickable months, newest first: [(key, year, month), ...]."""
    today = today or dt.date.today()
    out = []
    year, month = today.year, today.month
    for _ in range(count):
        if (year, month) < (EARLIEST_YEAR, 1):
            break
        out.append((month_key(year, month), year, month))
        year, month = shift_month(year, month, -1)
    return out


# --------------------------------------------------------------------------
# The spec
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    """How a calendar month selects the rows of one source.

    kind 'range'      -- `field` is a date/datetime column: first <= x < next,
                         bound as ISO strings like every Reporting date filter
                         (the legacy "SQL Server" ODBC driver cannot bind a
                         Python date: HYC00 "optional feature not implemented").
    kind 'text_month' -- `field` is text holding dd.MM.yyyy; contains '.MM.yyyy'
                         (the 0135 rule: the column cannot be read as a date).
    kind 'year_month' -- `field` is the year column, `month_field` the month
                         number (the pre-aggregated 0134 view).
    `basis` is the msgid that tells the reader which date the month follows.
    """

    kind: str
    field: str
    basis: str
    month_field: str | None = None

    def filters(self, year, month):
        if self.kind == "range":
            first, nxt = month_bounds(year, month)
            return [
                {"field": self.field, "op": "gte", "value": first.isoformat()},
                {"field": self.field, "op": "lt", "value": nxt.isoformat()},
            ]
        if self.kind == "text_month":
            return [{"field": self.field, "op": "contains", "value": f".{month:02d}.{year:04d}"}]
        if self.kind == "year_month":
            return [
                {"field": self.field, "op": "eq", "value": year},
                {"field": self.month_field, "op": "eq", "value": month},
            ]
        raise FinanceSpecError(f"unknown period kind: {self.kind!r}")

    def fields(self):
        return (self.field,) + ((self.month_field,) if self.month_field else ())


@dataclass(frozen=True)
class Breakdown:
    """One table under a block: the block's figures grouped by `dim`.

    `metrics` narrows the columns to a subset of the block's figures (a
    measure that is itself a split of another one is noise as a column).
    """

    dim: str
    label: str
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class Block:
    """Figures that share one month basis, plus their breakdown tables."""

    period: Period
    figures: tuple[str, ...]
    breakdowns: tuple[Breakdown, ...] = ()


@dataclass(frozen=True)
class Section:
    """One client / workbook on the page."""

    key: str
    client: str
    source: str
    blocks: tuple[Block, ...]
    group: str = INTERNAL
    title: str | None = None
    note: str | None = None


SECTIONS = (
    # ---- Internal customers: the six #329 workbooks, in their 0130-0135 order.
    Section(
        key="elektro_material",
        client="Elektro-Material",
        source="em_invoice",
        note=N_(
            "Live figures: EM_Invoice is still edited after a month closes, so a "
            "closed month can return different numbers later. Only the Opex and "
            "e-mail channels are billed."
        ),
        blocks=(
            Block(
                period=Period("range", "ExportEM_dt", basis=N_("by export date")),
                figures=("em_documents", "em_images_out", "em_order_positions"),
                breakdowns=(Breakdown("Eingang", N_("Channel")),),
            ),
        ),
    ),
    Section(
        key="compass",
        client="Compass Group",
        source="compass_invoice",
        note=N_(
            "Counted by upload date, whatever the document date: that is the set "
            "the invoice bills."
        ),
        blocks=(
            Block(
                period=Period("range", "UploadDatetime", basis=N_("by upload date")),
                figures=("compass_documents",),
            ),
        ),
    ),
    Section(
        key="privera_posteingang",
        client="Privera",
        title="Posteingang",
        source="privera_posteingang",
        note=N_(
            "The export date of this source is text, so the month is matched on "
            "its '.MM.yyyy' part."
        ),
        blocks=(
            Block(
                period=Period("text_month", "ExportDatetime", basis=N_("by export date")),
                figures=("privera_posteingang_documents",),
                breakdowns=(Breakdown("Niederlassung", N_("Branch")),),
            ),
        ),
    ),
    Section(
        key="privera_invoice",
        client="Privera",
        title="Rechnungseingang",
        source="privera_invoice",
        blocks=(
            Block(
                period=Period("range", "ExportDate", basis=N_("by export date")),
                figures=(
                    "privera_documents",
                    "privera_mail_documents",
                    "privera_ebill_documents",
                ),
                breakdowns=(
                    Breakdown("Mandant", N_("Mandant")),
                    Breakdown("DocSource", N_("Source"), metrics=("privera_documents",)),
                ),
            ),
        ),
    ),
    Section(
        key="privera_nachsendungen",
        client="Privera",
        title="Physische Zustellung",
        source="privera_nachsendungen",
        blocks=(
            Block(
                period=Period("range", "ExportDatetime", basis=N_("by export date")),
                figures=("privera_nachsendungen_total", "privera_nachsendungen_ohne_tec"),
                breakdowns=(Breakdown("Niederlassung", N_("Branch")),),
            ),
        ),
    ),
    Section(
        key="privera_neuzugaenge",
        client="Privera",
        title="Neuzugänge",
        source="privera_neuzugaenge",
        blocks=(
            Block(
                period=Period(
                    "year_month",
                    "JahrExport",
                    basis=N_("by export year and month"),
                    month_field="MonatExportNr",
                ),
                figures=(
                    "privera_neuzugaenge_dossiers",
                    "privera_neuzugaenge_register",
                    "privera_neuzugaenge_seiten",
                ),
                breakdowns=(Breakdown("Niederlassung", N_("Branch")),),
            ),
        ),
    ),
    # ---- External clients: what their collectors already deliver.
    Section(
        key="frigemo",
        client="Frigemo",
        source="frigemo",
        group=EXTERNAL,
        blocks=(
            Block(
                period=Period("range", "DCD", basis=N_("by date")),
                figures=(
                    "frigemo_imported_docs",
                    "frigemo_exported_docs",
                    "frigemo_imported_pages",
                    "frigemo_exported_pages",
                    "frigemo_invoices",
                    "frigemo_deleted",
                ),
            ),
        ),
    ),
    Section(
        key="xpert",
        client="Aveniq",
        title="Xpert",
        source="xpert_stats",
        group=EXTERNAL,
        blocks=(
            Block(
                period=Period("range", "ExportDate", basis=N_("by date")),
                figures=(
                    "xpert_stats_documents",
                    "xpert_stats_bfh_new_creditors",
                    "xpert_stats_zhaw_workitems",
                ),
                breakdowns=(
                    Breakdown("Client", N_("Client"), metrics=("xpert_stats_documents",)),
                    Breakdown(
                        "SourceDb", N_("Source database"), metrics=("xpert_stats_documents",)
                    ),
                ),
            ),
        ),
    ),
    Section(
        key="bucherer",
        client="Bucherer",
        title="EasyTax",
        source="bucherer_easytax",
        group=EXTERNAL,
        blocks=(
            Block(
                period=Period("range", "ImportTime", basis=N_("by import date")),
                figures=("bucherer_easytax_imported", "bucherer_easytax_pages"),
            ),
            Block(
                period=Period("range", "ExportTime", basis=N_("by export date")),
                figures=("bucherer_easytax_exported",),
            ),
        ),
    ),
    Section(
        key="mediamarkt",
        client="MediaMarkt",
        source="mediamarkt_batches",
        group=EXTERNAL,
        blocks=(
            Block(
                period=Period("range", "ScanDate", basis=N_("by scan date")),
                figures=("mediamarkt_batches", "mediamarkt_pieces"),
                breakdowns=(Breakdown("DocType", N_("Type (K/D/KA)")),),
            ),
        ),
    ),
    # ---- Sydoc's own services: the hours booked in the BPS timetool.
    Section(
        key="bps",
        client="Sydoc",
        title="BPS",
        source="bps_projects",
        group=SERVICES,
        note=N_(
            "Hours booked in the BPS timetool. Service hours are everything except "
            "the Absences pseudo-customer (vacation, sick leave, compensation), "
            "which is shown separately. The task names are BPS's own."
        ),
        blocks=(
            Block(
                period=Period("range", "Datum", basis=N_("by booking date")),
                figures=(
                    "bps_projects_service_hours",
                    "bps_projects_absence_hours",
                    "bps_projects_hours",
                ),
                breakdowns=(
                    Breakdown("Aufgabe", N_("Task"), metrics=("bps_projects_service_hours",)),
                    Breakdown("Kunde", N_("Customer"), metrics=("bps_projects_service_hours",)),
                ),
            ),
        ),
    ),
)

SECTIONS_BY_KEY = {s.key: s for s in SECTIONS}


def section_descriptors():
    """The static shape of the page: what the template renders before any data."""
    return [
        {"key": s.key, "client": s.client, "title": s.title, "group": s.group, "source": s.source}
        for s in SECTIONS
    ]


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """One SQL statement of a section run, and what its rows mean."""

    block: int
    kind: str  # 'figures' (this month) | 'previous' (the month before) | 'breakdown'
    dim: str | None
    metrics: tuple[str, ...]
    sql: str
    params: list


def _refs(codes):
    return [{"metric": code} for code in codes]


def build_section_queries(section, base_object, catalog, source_metrics, year, month):
    """Every query one section needs for (year, month), in a fixed order.

    `catalog` is the source's field catalog (table_source_catalog output) and
    `source_metrics` its metric registry ({code: {aggregation, base_field,
    filter, ...}}) -- the same two inputs Reporting's run path resolves a
    definition against. Raises FinanceSpecError when the spec names a field
    the catalog lacks, and lets MetricResolveError / TableQueryError through
    for an unknown measure or an unsafe identifier: a misconfigured section
    must fail loudly, never quietly return a grand total in place of a
    breakdown.
    """
    catalog_fields = {f["field"] for f in catalog}
    prev_year, prev_month = shift_month(year, month, -1)
    out = []
    for index, block in enumerate(section.blocks):
        for f in block.period.fields():
            if f not in catalog_fields:
                raise FinanceSpecError(f"{section.key}: period field {f!r} is not in the catalog")
        resolved = resolve_metrics(_refs(block.figures), source_metrics, catalog_fields)
        for kind, (y, m) in (("figures", (year, month)), ("previous", (prev_year, prev_month))):
            rd = {
                "columns": [],
                "filters": block.period.filters(y, m),
                "metrics": _refs(block.figures),
                "sort": [],
            }
            sql, params = build_generic_query(
                rd, base_object, catalog, row_cap=1, resolved_metrics=resolved
            )
            out.append(Query(index, kind, None, block.figures, sql, params))
        for br in block.breakdowns:
            if br.dim not in catalog_fields:
                raise FinanceSpecError(f"{section.key}: dimension {br.dim!r} is not in the catalog")
            codes = br.metrics or block.figures
            for code in codes:
                if code not in block.figures:
                    raise FinanceSpecError(
                        f"{section.key}: breakdown measure {code!r} is not one of the block's figures"
                    )
            resolved_b = resolve_metrics(_refs(codes), source_metrics, catalog_fields)
            rd = {
                "columns": [{"field": br.dim}],
                "filters": block.period.filters(year, month),
                "metrics": _refs(codes),
                "sort": [{"field": codes[0], "dir": "desc"}],
            }
            sql, params = build_generic_query(
                rd, base_object, catalog, row_cap=BREAKDOWN_ROW_CAP, resolved_metrics=resolved_b
            )
            out.append(Query(index, "breakdown", br.dim, codes, sql, params))
    return out


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------


def _number(value):
    """A DB aggregate cell as a JSON number: NULL (an empty SUM) counts as 0."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float):
        # Hours come back as decimals; summing them in floats leaves noise
        # like 0.30000000000000004 -- four places is BPS's own precision.
        return int(value) if value.is_integer() else round(value, 4)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _cells(rows, width):
    """The single aggregate row of a figures query as numbers (all 0 when empty)."""
    row = rows[0] if rows else []
    return [_number(row[i]) if i < len(row) else 0 for i in range(width)]


def _breakdown_rows(rows):
    """Grouped rows -> [{key, values}], dropping groups that counted nothing."""
    out = []
    for row in rows:
        values = [_number(v) for v in row[1:]]
        if not any(values):
            continue
        key = row[0]
        out.append({"key": None if key is None else str(key), "values": values})
    return out


def assemble_section(section, queries, rows_by_query, *, source_label, metric_label, translate):
    """Fold the executed queries of one section into the page payload.

    `rows_by_query` is aligned with `queries` (build_section_queries output).
    `metric_label(code)` returns the measure's display name in the reader's
    locale, `translate(msgid)` renders the marked spec strings.
    """
    by_key = {
        (q.block, q.kind, q.dim): rows for q, rows in zip(queries, rows_by_query, strict=True)
    }
    blocks = []
    for index, block in enumerate(section.blocks):
        width = len(block.figures)
        current = _cells(by_key.get((index, "figures", None), []), width)
        previous = _cells(by_key.get((index, "previous", None), []), width)
        figures = [
            {"code": code, "label": metric_label(code), "value": current[i], "prev": previous[i]}
            for i, code in enumerate(block.figures)
        ]
        breakdowns = []
        for br in block.breakdowns:
            codes = br.metrics or block.figures
            rows = _breakdown_rows(by_key.get((index, "breakdown", br.dim), []))
            totals = [_number(sum(r["values"][i] for r in rows)) for i in range(len(codes))]
            breakdowns.append(
                {
                    "dim": br.dim,
                    "label": translate(br.label),
                    "columns": [{"code": c, "label": metric_label(c)} for c in codes],
                    "rows": rows,
                    "totals": totals,
                }
            )
        blocks.append(
            {"basis": translate(block.period.basis), "figures": figures, "breakdowns": breakdowns}
        )
    return {
        "key": section.key,
        "client": section.client,
        "title": section.title,
        "group": section.group,
        "source": {"code": section.source, "label": source_label},
        "note": translate(section.note) if section.note else None,
        "blocks": blocks,
        "error": None,
    }


def error_section(section, message, *, detail=None, source_label=None):
    """The payload of a section that could not be read -- the page shows it in place."""
    return {
        "key": section.key,
        "client": section.client,
        "title": section.title,
        "group": section.group,
        "source": {"code": section.source, "label": source_label},
        "note": None,
        "blocks": [],
        "error": message,
        "detail": detail,
    }


def export_rows(payload):
    """A section payload as flat CSV rows: one per figure and per breakdown cell.

    Column order matches export_columns(): client, section, month basis, kind,
    dimension, group, measure, value, previous month.
    """
    section = payload.get("title") or ""
    out = []
    if payload.get("error"):
        out.append([payload["client"], section, "", "error", "", "", payload["error"], "", ""])
        return out
    for block in payload["blocks"]:
        out.extend(
            [
                payload["client"],
                section,
                block["basis"],
                "figure",
                "",
                "",
                f["label"],
                f["value"],
                f["prev"],
            ]
            for f in block["figures"]
        )
        for br in block["breakdowns"]:
            for row in br["rows"]:
                group = "" if row["key"] is None else row["key"]
                out.extend(
                    [
                        payload["client"],
                        section,
                        block["basis"],
                        "breakdown",
                        br["label"],
                        group,
                        col["label"],
                        value,
                        "",
                    ]
                    for col, value in zip(br["columns"], row["values"], strict=True)
                )
    return out
