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

from . import bps
from .reporting.semantic import resolve_metrics
from .reporting.table_query import build_generic_query

EARLIEST_YEAR = 2020
MONTH_OPTIONS = 36
BREAKDOWN_ROW_CAP = 1000
BOOKINGS_ROW_CAP = 5000

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
    With `across` set it is a matrix instead: one measure (the first of
    `metrics`, or of the block) grouped by `dim` down and `across` along --
    the shape the Privera "Versand" sheets bill (register x branch).
    """

    dim: str
    label: str
    metrics: tuple[str, ...] = ()
    across: str | None = None
    across_label: str | None = None


@dataclass(frozen=True)
class Block:
    """Figures that share one month basis, plus their breakdown tables."""

    period: Period
    figures: tuple[str, ...]
    breakdowns: tuple[Breakdown, ...] = ()


@dataclass(frozen=True)
class Bookings:
    """Every row of a source that matches one of `rules`, listed singly.

    For services billed per booking (the BPS hours): accounting needs each
    line with its comment, not a total. `rules` are AND-groups in the
    Reporting filter grammar, OR-ed by running one query per group -- they
    must be disjoint (bps.BILLABLE_RULES is). `hours` is the column summed
    into the figures, `group_by` the column the list is grouped by.
    """

    period: Period
    rules: tuple[tuple[dict, ...], ...]
    columns: tuple[str, ...]
    hours: str
    group_by: str
    sort: tuple[str, ...]
    labels: tuple[str, ...]


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
    bookings: Bookings | None = None
    link: str | None = None
    # The short label of the page's jump index; falls back to title, then client.
    nav: str | None = None


SECTIONS = (
    # ---- Internal customers: the six #329 workbooks, in their 0130-0135 order.
    Section(
        key="elektro_material",
        client="Elektro-Material",
        source="em_invoice",
        note=N_(
            "EM_Invoice is still edited after a month ends: a re-exported document "
            "moves to the month of its new export date. Close the month once it is "
            "invoiced so its figures stay as billed. Only the Opex and e-mail "
            "channels are billed."
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
        nav="Compass",
        source="compass_invoice",
        note=N_(
            "Counted by upload date, whatever the document date: that is the set "
            "the invoice bills. Rows without a workitem that repeat a barcode "
            "(74 in August 2026) are counted, as the workbook counts them."
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
                breakdowns=(
                    Breakdown("Niederlassung", N_("Branch")),
                    Breakdown(
                        "Register",
                        N_("Register"),
                        across="Niederlassung",
                        across_label=N_("Branch"),
                    ),
                ),
            ),
        ),
    ),
    Section(
        key="privera_invoice",
        client="Privera",
        title="Rechnungseingang",
        nav="Rechnungen",
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
        nav="Zustellung",
        source="privera_nachsendungen",
        blocks=(
            Block(
                period=Period("range", "ExportDatetime", basis=N_("by export date")),
                figures=("privera_nachsendungen_total", "privera_nachsendungen_ohne_tec"),
                breakdowns=(
                    Breakdown("Niederlassung", N_("Branch")),
                    Breakdown(
                        "Nachsendungstyp",
                        N_("Forwarding type"),
                        metrics=("privera_nachsendungen_total",),
                        across="Niederlassung",
                        across_label=N_("Branch"),
                    ),
                ),
            ),
        ),
    ),
    Section(
        key="privera_neuzugaenge",
        client="Privera",
        title="Neuzugänge",
        source="privera_neuzugaenge",
        note=N_(
            "A dossier registered under two branches is counted in both, exactly "
            "as the workbook counts it."
        ),
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
    # ---- Sydoc's own services: the billable hours booked in the BPS timetool.
    Section(
        key="bps",
        client="Sydoc",
        title=N_("Billable services"),
        nav=N_("Services"),
        source=bps.SOURCE,
        group=SERVICES,
        link="bps",
        note=N_(
            "Every billable booking of the BPS timetool, singly and with its comment: "
            "Support (verrechenbar, extern verrechenbar), Change, Change Request, "
            "Professional Services and Projektmanagement on customers, plus "
            "Vorbereitung Akten on Privera · Tagesgeschäft Neuzugänge. All hours, "
            "drilled down per task, customer and person, are on the Sydoc BPS page."
        ),
        blocks=(),
        bookings=Bookings(
            period=Period("range", "Datum", basis=N_("by booking date")),
            rules=bps.BILLABLE_RULES,
            columns=bps.BOOKING_COLUMNS,
            hours="Stunden",
            group_by="Kunde",
            sort=("Kunde", "Datum", "Benutzer"),
            labels=(
                N_("Date"),
                N_("Customer"),
                N_("Package"),
                N_("Task"),
                N_("Person"),
                N_("Hours"),
                N_("Comment"),
            ),
        ),
    ),
)

SECTIONS_BY_KEY = {s.key: s for s in SECTIONS}


def billed_clients():
    """The Finance clients a Bexio invoice is addressed to, in page order (#423).

    One per distinct Section.client; Sydoc's own BPS services are billed on the
    customers' invoices, so the SERVICES group names no client of its own.
    """
    seen: dict[str, None] = {}
    for s in SECTIONS:
        if s.group != SERVICES:
            seen.setdefault(s.client, None)
    return list(seen)


def section_descriptors():
    """The static shape of the page: what the template renders before any data."""
    return [
        {
            "key": s.key,
            "client": s.client,
            "title": s.title,
            "group": s.group,
            "source": s.source,
            "link": s.link,
            "nav": s.nav or s.title or s.client,
        }
        for s in SECTIONS
    ]


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """One SQL statement of a section run, and what its rows mean."""

    block: int
    kind: str  # figures | previous | breakdown | matrix | bookings | bookings_figures | bookings_previous
    dim: str | None
    metrics: tuple[str, ...]
    sql: str
    params: list


def _refs(codes):
    return [{"metric": code} for code in codes]


def _check_fields(section, catalog_fields, fields, what):
    for f in fields:
        if f not in catalog_fields:
            raise FinanceSpecError(f"{section.key}: {what} {f!r} is not in the catalog")


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
        _check_fields(section, catalog_fields, block.period.fields(), "period field")
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
            _check_fields(section, catalog_fields, (br.dim,), "dimension")
            codes = br.metrics or block.figures
            for code in codes:
                if code not in block.figures:
                    raise FinanceSpecError(
                        f"{section.key}: breakdown measure {code!r} is not one of the block's figures"
                    )
            dims = [br.dim]
            if br.across:
                _check_fields(section, catalog_fields, (br.across,), "matrix dimension")
                codes = codes[:1]
                dims.append(br.across)
            resolved_b = resolve_metrics(_refs(codes), source_metrics, catalog_fields)
            rd = {
                "columns": [{"field": d} for d in dims],
                "filters": block.period.filters(year, month),
                "metrics": _refs(codes),
                "sort": [{"field": codes[0], "dir": "desc"}],
            }
            sql, params = build_generic_query(
                rd, base_object, catalog, row_cap=BREAKDOWN_ROW_CAP, resolved_metrics=resolved_b
            )
            kind = "matrix" if br.across else "breakdown"
            out.append(Query(index, kind, br.dim, codes, sql, params))
    if section.bookings is not None:
        out.extend(_bookings_queries(section, base_object, catalog, catalog_fields, year, month))
    return out


def _bookings_queries(section, base_object, catalog, catalog_fields, year, month):
    """Per rule: the rows of the month, and the hours/count of this and the previous month.

    The figures are aggregates of their own rather than sums of the listed
    rows, so a list cut at BOOKINGS_ROW_CAP still totals correctly.
    """
    bk = section.bookings
    _check_fields(section, catalog_fields, bk.period.fields(), "period field")
    _check_fields(section, catalog_fields, bk.columns, "bookings column")
    _check_fields(section, catalog_fields, (bk.hours, bk.group_by, *bk.sort), "bookings field")
    for rule in bk.rules:
        _check_fields(section, catalog_fields, [c["field"] for c in rule], "bookings rule field")
    totals = {
        "hours": {"aggregation": "sum", "base_field": bk.hours, "filter": None},
        "count": {"aggregation": "count", "base_field": None, "filter": None},
    }
    resolved = resolve_metrics(_refs(("hours", "count")), totals, catalog_fields)
    prev_year, prev_month = shift_month(year, month, -1)
    out = []
    for index, rule in enumerate(bk.rules):
        rd = {
            "columns": [{"field": c} for c in bk.columns],
            "filters": bk.period.filters(year, month) + [dict(c) for c in rule],
            "sort": [{"field": f, "dir": "asc"} for f in bk.sort],
        }
        sql, params = build_generic_query(rd, base_object, catalog, row_cap=BOOKINGS_ROW_CAP)
        out.append(Query(index, "bookings", None, (), sql, params))
        for kind, (y, m) in (
            ("bookings_figures", (year, month)),
            ("bookings_previous", (prev_year, prev_month)),
        ):
            rd = {
                "columns": [],
                "filters": bk.period.filters(y, m) + [dict(c) for c in rule],
                "metrics": _refs(("hours", "count")),
                "sort": [],
            }
            sql, params = build_generic_query(
                rd, base_object, catalog, row_cap=1, resolved_metrics=resolved
            )
            out.append(Query(index, kind, None, ("hours", "count"), sql, params))
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


def _key(value):
    return None if value is None else str(value)


def _breakdown_rows(rows):
    """Grouped rows -> [{key, values}], dropping groups that counted nothing."""
    out = []
    for row in rows:
        values = [_number(v) for v in row[1:]]
        if not any(values):
            continue
        out.append({"key": _key(row[0]), "values": values})
    return out


def _sorted_keys(totals):
    """Keys alphabetically, the blank group last -- the order of the workbooks' pivots."""
    return sorted(totals, key=lambda k: (k is None, (k or "").casefold()))


def _matrix(rows):
    """(dim, across, value) rows -> a dense pivot with row and column totals."""
    cells: dict[tuple, int | float] = {}
    row_tot: dict[str | None, int | float] = {}
    col_tot: dict[str | None, int | float] = {}
    for row in rows:
        value = _number(row[2]) if len(row) > 2 else 0
        if not value:
            continue
        r, c = _key(row[0]), _key(row[1])
        cells[(r, c)] = _number(cells.get((r, c), 0) + value)
        row_tot[r] = _number(row_tot.get(r, 0) + value)
        col_tot[c] = _number(col_tot.get(c, 0) + value)
    row_keys, col_keys = _sorted_keys(row_tot), _sorted_keys(col_tot)
    return {
        "row_keys": row_keys,
        "col_keys": col_keys,
        "cells": [[cells.get((r, c), 0) for c in col_keys] for r in row_keys],
        "row_totals": [row_tot[r] for r in row_keys],
        "col_totals": [col_tot[c] for c in col_keys],
        "total": _number(sum(row_tot.values())),
    }


def _cell_value(value):
    """A row-level cell as JSON: dates as ISO, numbers as numbers, text cleaned."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        return _number(value)
    return bps.clean_text(value)


def _assemble_bookings(section, by_key, translate):
    bk = section.bookings
    cols = list(bk.columns)
    hours_i, group_i = cols.index(bk.hours), cols.index(bk.group_by)
    name_i = cols.index("Benutzer") if "Benutzer" in cols else None
    task_i = cols.index("Aufgabe") if "Aufgabe" in cols else None
    rows, truncated = [], False
    current, previous = [0, 0], [0, 0]
    for index in range(len(bk.rules)):
        raw = by_key.get((index, "bookings", None), [])
        truncated = truncated or len(raw) >= BOOKINGS_ROW_CAP
        for r in raw:
            cells = [_cell_value(v) for v in r]
            if name_i is not None:
                cells[name_i] = bps.clean_name(cells[name_i])
            rows.append(cells)
        for acc, kind in ((current, "bookings_figures"), (previous, "bookings_previous")):
            h, n = _cells(by_key.get((index, kind, None), []), 2)
            acc[0] = _number(acc[0] + h)
            acc[1] = _number(acc[1] + n)
    sort_i = [cols.index(f) for f in bk.sort]
    rows.sort(key=lambda r: tuple("" if r[i] is None else str(r[i]).casefold() for i in sort_i))
    groups: dict = {}
    order: list = []
    by_task: dict = {}
    for r in rows:
        key = r[group_i]
        if key not in groups:
            groups[key] = {"key": key, "hours": 0, "count": 0, "rows": []}
            order.append(key)
        g = groups[key]
        g["hours"] = _number(g["hours"] + (r[hours_i] or 0))
        g["count"] += 1
        g["rows"].append(r)
        if task_i is not None:
            t = by_task.setdefault(r[task_i], {"key": r[task_i], "hours": 0, "count": 0})
            t["hours"] = _number(t["hours"] + (r[hours_i] or 0))
            t["count"] += 1
    return {
        "basis": translate(bk.period.basis),
        "figures": [
            {
                "code": "billable_hours",
                "label": translate(N_("Billable hours")),
                "value": current[0],
                "prev": previous[0],
            },
            {
                "code": "billable_bookings",
                "label": translate(N_("Billable bookings")),
                "value": current[1],
                "prev": previous[1],
            },
        ],
        "columns": [
            {"field": f, "label": translate(label), "numeric": f == bk.hours}
            for f, label in zip(bk.columns, bk.labels, strict=True)
        ],
        "group_by": bk.group_by,
        "groups": [groups[k] for k in order],
        "by_task": sorted(by_task.values(), key=lambda t: (-t["hours"], t["key"] or "")),
        "truncated": truncated,
    }


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
            if br.across:
                code = codes[0]
                breakdowns.append(
                    {
                        "kind": "matrix",
                        "dim": br.dim,
                        "across": br.across,
                        "label": translate(br.label),
                        "across_label": translate(br.across_label or br.across),
                        "measure": {"code": code, "label": metric_label(code)},
                        **_matrix(by_key.get((index, "matrix", br.dim), [])),
                    }
                )
                continue
            rows = _breakdown_rows(by_key.get((index, "breakdown", br.dim), []))
            totals = [_number(sum(r["values"][i] for r in rows)) for i in range(len(codes))]
            breakdowns.append(
                {
                    "kind": "table",
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
        "title": translate(section.title) if section.title else None,
        "group": section.group,
        "source": {"code": section.source, "label": source_label},
        "note": translate(section.note) if section.note else None,
        "blocks": blocks,
        "bookings": _assemble_bookings(section, by_key, translate) if section.bookings else None,
        "error": None,
    }


def error_section(section, message, *, detail=None, source_label=None, translate=None):
    """The payload of a section that could not be read -- the page shows it in place."""
    title = section.title
    if title and translate:
        title = translate(title)
    return {
        "key": section.key,
        "client": section.client,
        "title": title,
        "group": section.group,
        "source": {"code": section.source, "label": source_label},
        "note": None,
        "blocks": [],
        "bookings": None,
        "error": message,
        "detail": detail,
    }


# --------------------------------------------------------------------------
# Month close
# --------------------------------------------------------------------------


def payload_figures(payload):
    """{(block, code): (label, value)} of every figure a payload shows, bookings included."""
    out: dict[tuple, tuple] = {}
    for index, block in enumerate(payload.get("blocks") or []):
        for f in block.get("figures") or []:
            out[(index, f["code"])] = (f["label"], f["value"])
    for f in (payload.get("bookings") or {}).get("figures") or []:
        out[("bookings", f["code"])] = (f["label"], f["value"])
    return out


def diff_payload(closed, live):
    """Where the live figures of a closed month moved away from its snapshot.

    [{label, closed, live}] in the snapshot's order; empty when nothing moved.
    A figure that exists on only one side is reported with 0 on the other.
    """
    a, b = payload_figures(closed), payload_figures(live)
    out = []
    for key in list(a) + [k for k in b if k not in a]:
        label = (a.get(key) or b.get(key))[0]
        va = a[key][1] if key in a else 0
        vb = b[key][1] if key in b else 0
        if va != vb:
            out.append({"label": label, "closed": va, "live": vb})
    return out


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

EXPORT_WIDTH = 10


def _export_line(
    client, section, basis, kind, dim="", group="", measure="", value="", prev="", detail=""
):
    return [client, section, basis, kind, dim, group, measure, value, prev, detail]


def export_rows(payload):
    """A section payload as flat CSV rows: one per figure, breakdown cell and booking.

    Column order matches the export's header: client, section, month basis,
    kind, dimension, group, measure, value, previous month, detail. A matrix
    cell's group is "row / column"; a booking's group is its customer, its
    measure the task, its value the hours, and date, package, person and
    comment follow in `detail`.
    """
    section = payload.get("title") or ""
    client = payload["client"]
    if payload.get("error"):
        return [_export_line(client, section, "", "error", measure=payload["error"])]
    out: list[list] = []
    for block in payload["blocks"]:
        basis = block["basis"]
        out.extend(
            _export_line(
                client,
                section,
                basis,
                "figure",
                measure=f["label"],
                value=f["value"],
                prev=f["prev"],
            )
            for f in block["figures"]
        )
        for br in block["breakdowns"]:
            if br.get("kind") == "matrix":
                dim = f"{br['label']} x {br['across_label']}"
                for r, rk in enumerate(br["row_keys"]):
                    for c, ck in enumerate(br["col_keys"]):
                        if br["cells"][r][c]:
                            out.append(
                                _export_line(
                                    client,
                                    section,
                                    basis,
                                    "matrix",
                                    dim,
                                    f"{rk or ''} / {ck or ''}",
                                    br["measure"]["label"],
                                    br["cells"][r][c],
                                )
                            )
                continue
            for row in br["rows"]:
                group = "" if row["key"] is None else row["key"]
                out.extend(
                    _export_line(
                        client, section, basis, "breakdown", br["label"], group, col["label"], value
                    )
                    for col, value in zip(br["columns"], row["values"], strict=True)
                )
    bk = payload.get("bookings")
    if bk:
        basis = bk["basis"]
        out.extend(
            _export_line(
                client,
                section,
                basis,
                "figure",
                measure=f["label"],
                value=f["value"],
                prev=f["prev"],
            )
            for f in bk["figures"]
        )
        idx = {c["field"]: i for i, c in enumerate(bk["columns"])}
        skip = {bk["group_by"], "Aufgabe", "Stunden"}
        detail_fields = [f for f in idx if f not in skip]
        for g in bk["groups"]:
            for row in g["rows"]:
                detail = " · ".join(
                    str(row[idx[f]]) for f in detail_fields if row[idx[f]] not in (None, "")
                )
                out.append(
                    _export_line(
                        client,
                        section,
                        basis,
                        "booking",
                        bk["group_by"],
                        "" if g["key"] is None else g["key"],
                        row[idx["Aufgabe"]] if "Aufgabe" in idx else "",
                        row[idx["Stunden"]] if "Stunden" in idx else "",
                        "",
                        detail,
                    )
                )
    return out
