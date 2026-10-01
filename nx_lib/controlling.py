"""Sydoc Controlling -- margin per client stream: BPS hours x rate against Bexio (#433).

Pure and DB-free like nx_lib/finance.py and nx_lib/bps.py. It replaces the
hand-filled Projektcontrolling_Betriebskosten.xlsx: one sheet per client
stream with its hours per task, the hourly rate, what was invoiced, and the
difference, plus an Overview of the margins month by month.

Four inputs, all injected by the view:

* **Hours** -- every hour booked in BPS (the ``bps_projects`` source, all
  tasks, as the workbook counts them -- Pause and Zupfen included), mapped
  to a stream by customer and project package (``Stream.hours``) with the
  task-level exceptions of ``REASSIGN``.
* **Rates** -- ``dbo.FinanceRates``: the CHF per hour valid in a month
  (a per-stream override beats the default) and the hours of one FTE per
  working day.
* **Invoices** -- Bexio, read live (it is the system of record). An invoice
  belongs to a stream through its Bexio *project* (``dbo.ControllingStreamProjects``):
  the titles do not tell Privera's three invoices apart, the projects do.
  The invoice for month M is dated in M+1 (``bexio.INVOICE_MONTH_OFFSET``).
* **Documents** -- the Finance page's figure for the stream (``Documents``),
  read with the Finance section's own period, or taken from its month-close
  snapshot when the month is closed.

A figure that cannot be computed is never shown as 0: every stream month
carries a ``state`` (invoiced / draft / missing / foreign / unlinked / error)
and flags (no rate, incomplete source).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from . import bexio, bps, finance
from .finance import N_, month_key, shift_month
from .reporting.semantic import resolve_metrics
from .reporting.table_query import build_generic_query

#: The oldest month the page offers: the BPS history starts in January 2025.
EARLIEST = (2025, 1)

HOURLY = "hourly"
FTE_DAY_HOURS = "fte_day_hours"
RATE_KINDS = (HOURLY, FTE_DAY_HOURS)

#: Bexio states of a stream month (bexio.INVOICED / DRAFT_ONLY / MISSING / UNLINKED
#: plus two of this page's own).
INVOICED = bexio.INVOICED
DRAFT = bexio.DRAFT_ONLY
MISSING = bexio.MISSING
UNLINKED = bexio.UNLINKED
FOREIGN = "foreign"
ERROR = "error"

#: Sydoc reports in CHF. An issued invoice in another currency (Bucherer bills
#: in EUR) is not converted: the month is FOREIGN, its amount is shown in its
#: own currency and left out of every total (#433 design review).
HOME_CURRENCY = "CHF"

#: The task whose hours the per-document KPIs divide (the workbook's "Zeit pro Dok").
VALIDATION_TASK = "Validierung"

HOURS_ROW_CAP = 50000
DOCUMENTS_ROW_CAP = 1000

CENT = Decimal("0.01")


class ControllingSpecError(ValueError):
    """A stream names something its registered source does not carry."""


# --------------------------------------------------------------------------
# The spec
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Documents:
    """The documents a stream processed: one figure of a Finance section.

    `section` is the Finance section (its source and month basis are reused),
    `metric` one of its measures, `where` narrows a shared source to one
    client (Xpert's ZHAW and BFH), `block` the section block whose period
    applies.
    """

    section: str
    metric: str
    where: tuple[dict, ...] = ()
    block: int = 0

    @property
    def finance_section(self):
        return finance.SECTIONS_BY_KEY[self.section]

    @property
    def period(self):
        return self.finance_section.blocks[self.block].period


#: The default unit of a stream's documents.
DOCUMENTS = N_("documents")


@dataclass(frozen=True)
class Stream:
    """One row of the page: one sheet of the workbook.

    `hours` lists the BPS (customer, project package) pairs booked on the
    stream; a package of None takes every package of that customer that no
    other stream names. Aveniq's packages (BFH, ZHAW, HAP, ...) are its
    DocProStar mandants and belong to no stream, as in the workbook.

    `client` and `title` are the block heading ("Privera" + "Posteingang"),
    `nav` the short label of the task matrix, `unit` (a msgid) what the
    documents count.
    """

    key: str
    label: str
    client: str
    hours: tuple[tuple[str, str | None], ...]
    documents: Documents | None = None
    title: str | None = None
    nav: str | None = None
    unit: str = DOCUMENTS


STREAMS = (
    Stream(
        key="elektro_material",
        label="Elektro-Material",
        client="Elektro-Material",
        hours=(("Elektro Material", None),),
        documents=Documents("elektro_material", "em_documents"),
    ),
    Stream(
        key="compass",
        label="Compass Group",
        client="Compass Group",
        nav="Compass",
        hours=(("CompassGroup", None),),
        documents=Documents("compass", "compass_documents"),
    ),
    Stream(
        key="privera_posteingang",
        label="Privera Posteingang",
        client="Privera",
        title="Posteingang",
        nav="Posteingang",
        hours=(("Privera", "Posteingang"), ("Privera", "Tagesgeschäft Posteingang")),
        documents=Documents("privera_posteingang", "privera_posteingang_documents"),
    ),
    Stream(
        key="privera_invoice",
        label="Privera Rechnungseingang",
        client="Privera",
        title="Rechnungseingang",
        nav="Rechnungen",
        hours=(("Privera", "Invoice"), ("Privera", "Tagesgeschäft Invoice")),
        documents=Documents("privera_invoice", "privera_documents"),
    ),
    Stream(
        key="privera_neuzugaenge",
        label="Privera Neuzugänge",
        client="Privera",
        title="Neuzugänge",
        nav="Neuzugänge",
        hours=(("Privera", "Neuzugänge"), ("Privera", "Tagesgeschäft Neuzugänge")),
        documents=Documents("privera_neuzugaenge", "privera_neuzugaenge_dossiers"),
        unit=N_("dossiers"),
    ),
    Stream(
        key="frigemo",
        label="Frigemo",
        client="Frigemo",
        hours=(("Frigemo", None),),
        documents=Documents("frigemo", "frigemo_imported_docs"),
    ),
    Stream(
        key="zhaw",
        label="ZHAW",
        client="ZHAW",
        title=N_("via Xpert"),
        hours=(("ZHAW", None),),
        documents=Documents(
            "xpert",
            "xpert_stats_documents",
            where=({"field": "Client", "op": "eq", "value": "ZHAW"},),
        ),
    ),
    Stream(
        key="bfh",
        label="BFH",
        client="BFH",
        hours=(("BFH", None),),
        documents=Documents(
            "xpert",
            "xpert_stats_documents",
            where=({"field": "Client", "op": "eq", "value": "BFH"},),
        ),
    ),
    Stream(
        key="bucherer",
        label="Bucherer",
        client="Bucherer",
        hours=(("Bucherer", None),),
        documents=Documents("bucherer", "bucherer_easytax_imported"),
    ),
    Stream(
        key="mediamarkt",
        label="MediaMarkt",
        client="MediaMarkt",
        hours=(("MediaMarkt", None),),
        documents=Documents("mediamarkt", "mediamarkt_pieces"),
        unit=N_("pieces"),
    ),
)

STREAMS_BY_KEY = {s.key: s for s in STREAMS}

#: Task-level exceptions to the package mapping: (customer, task) -> stream.
#: BPS books Privera's Zupfen on "Tagesgeschäft Invoice"; the workbook has
#: always counted it under Posteingang, and the workbook is the truth (#433).
REASSIGN = ((("Privera", "Zupfen"), "privera_posteingang"),)


@dataclass(frozen=True)
class Incomplete:
    """Stream months whose BPS hours are known to fall short of the truth."""

    streams: tuple[str, ...]
    first: tuple[int, int]
    last: tuple[int, int]
    note: str


INCOMPLETE = (
    Incomplete(
        streams=("privera_posteingang", "privera_invoice", "privera_neuzugaenge"),
        first=(2025, 1),
        last=(2025, 10),
        note=N_(
            "BPS has fewer hours than the controlling workbook for this month: "
            "the bookings were never in the timetool, so cost and margin are too favourable."
        ),
    ),
)


def incomplete_note(stream_key, year, month):
    for inc in INCOMPLETE:
        if stream_key in inc.streams and inc.first <= (year, month) <= inc.last:
            return inc.note
    return None


def customers():
    """The BPS customers any stream books on, sorted."""
    return sorted({c for s in STREAMS for c, _p in s.hours})


def _n(value):
    return bps._norm(value)


_EXACT = {(_n(c), _n(p)): s.key for s in STREAMS for c, p in s.hours if p is not None}
_WHOLE = {_n(c): s.key for s in STREAMS for c, p in s.hours if p is None}
_REASSIGN = {(_n(c), _n(t)): key for (c, t), key in REASSIGN}


def stream_of(customer, package, task):
    """The stream key a BPS booking counts for, or None (reported as unmapped)."""
    key = _REASSIGN.get((_n(customer), _n(task)))
    if key:
        return key
    return _EXACT.get((_n(customer), _n(package))) or _WHOLE.get(_n(customer))


# --------------------------------------------------------------------------
# Months
# --------------------------------------------------------------------------


def parse_month(value, today=None):
    """Like finance.parse_month, clamped to EARLIEST."""
    year, month = finance.parse_month(value, today)
    return max((year, month), EARLIEST)


def months_between(first, last):
    """[(year, month), ...] from `first` to `last` inclusive."""
    out = []
    ym = first
    while ym <= last:
        out.append(ym)
        ym = shift_month(ym[0], ym[1], 1)
    return out


def working_days(year, month):
    """Monday-Friday days of a month (public holidays are not known here)."""
    first, nxt = finance.month_bounds(year, month)
    return sum(1 for i in range((nxt - first).days) if (first + dt.timedelta(i)).weekday() < 5)


def billed_month(invoice_date):
    """(year, month) an invoice dated `invoice_date` (ISO) bills."""
    if not invoice_date:
        return None
    y, m = int(invoice_date[:4]), int(invoice_date[5:7])
    return shift_month(y, m, -bexio.INVOICE_MONTH_OFFSET)


# --------------------------------------------------------------------------
# Hours
# --------------------------------------------------------------------------

_HOURS = {"hours": {"aggregation": "sum", "base_field": "Stunden", "filter": None}}


def hours_query(base_object, catalog, first, last):
    """Hours per month x customer x package x task for months first..last
    (inclusive (year, month) pairs), on the streams' customers only."""
    fields = bps._require(catalog, ("Datum", "Kunde", "Projektpaket", "Aufgabe", "Stunden"))
    resolved = resolve_metrics([{"metric": "hours"}], _HOURS, fields)
    start, _ = finance.month_bounds(*first)
    _, end = finance.month_bounds(*last)
    rd = {
        "columns": [
            {"field": "Datum", "grain": "month"},
            {"field": "Kunde"},
            {"field": "Projektpaket"},
            {"field": "Aufgabe"},
        ],
        "filters": [
            {"field": "Datum", "op": "gte", "value": start.isoformat()},
            {"field": "Datum", "op": "lt", "value": end.isoformat()},
            {"field": "Kunde", "op": "in", "value": customers()},
        ],
        "metrics": [{"metric": "hours"}],
        "sort": [],
    }
    return build_generic_query(
        rd, base_object, catalog, row_cap=HOURS_ROW_CAP, resolved_metrics=resolved
    )


def _dec(value):
    if value is None:
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _task(value):
    return " ".join((bps.clean_text(value) or "").split()) or "?"


@dataclass
class Hours:
    """Folded hours: {(month key, stream): {task: Decimal}} and what fit no stream."""

    by: dict = field(default_factory=dict)
    unmapped: dict = field(default_factory=dict)

    def tasks(self, mkey, stream_key):
        return self.by.get((mkey, stream_key), {})

    def total(self, mkey, stream_key):
        return sum(self.tasks(mkey, stream_key).values(), Decimal(0))


def fold_hours(rows):
    """hours_query rows -> Hours. Names are cleaned so 'Support ' and 'Support' merge."""
    out = Hours()
    for r in rows:
        if r[0] is None:
            continue
        mkey = bps._day(r[0])[:7]
        customer, package, task = (bps.clean_text(v) or "" for v in r[1:4])
        hours = _dec(r[4])
        if not hours:
            continue
        key = stream_of(customer, package, task)
        name = _task(task)
        if key is None:
            bucket = out.unmapped.setdefault(mkey, {})
            k = (customer, package, name)
            bucket[k] = bucket.get(k, Decimal(0)) + hours
            continue
        tasks = out.by.setdefault((mkey, key), {})
        tasks[name] = tasks.get(name, Decimal(0)) + hours
    return out


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DocQuery:
    stream: str
    mode: str  # 'grain' (month, value) | 'pair' (year, month, value) | 'month' (value)
    month: tuple[int, int] | None
    sql: str
    params: list


def documents_queries(stream, base_object, catalog, source_metrics, months):
    """The queries that count a stream's documents for every month of `months`.

    A date-range period is one query grouped by month, the year+month view one
    query grouped by both, and a text date (Privera Posteingang) one query per
    month -- the builder cannot bucket text.
    """
    doc = stream.documents
    if doc is None or not months:
        return []
    fields = {c["field"]: c for c in catalog}
    period = doc.period
    for f in (*period.fields(), *(w["field"] for w in doc.where)):
        if f not in fields:
            raise ControllingSpecError(f"{stream.key}: field {f!r} is not in the catalog")
    refs = [{"metric": doc.metric}]
    resolved = resolve_metrics(refs, source_metrics, set(fields))
    where = [dict(w) for w in doc.where]
    first, last = min(months), max(months)

    def run(columns, filters, mode, month=None):
        rd = {"columns": columns, "filters": filters + where, "metrics": refs, "sort": []}
        sql, params = build_generic_query(
            rd, base_object, catalog, row_cap=DOCUMENTS_ROW_CAP, resolved_metrics=resolved
        )
        return DocQuery(stream.key, mode, month, sql, params)

    if period.kind == "range" and fields[period.field].get("grainable"):
        start, _ = finance.month_bounds(*first)
        _, end = finance.month_bounds(*last)
        filters = [
            {"field": period.field, "op": "gte", "value": start.isoformat()},
            {"field": period.field, "op": "lt", "value": end.isoformat()},
        ]
        return [run([{"field": period.field, "grain": "month"}], filters, "grain")]
    if period.kind == "year_month":
        filters = [
            {"field": period.field, "op": "gte", "value": first[0]},
            {"field": period.field, "op": "lte", "value": last[0]},
        ]
        columns = [{"field": period.field}, {"field": period.month_field}]
        return [run(columns, filters, "pair")]
    return [run([], period.filters(*ym), "month", ym) for ym in sorted(months)]


def fold_documents(queries, rows_by_query, months):
    """{(month key, stream): documents} for the months asked (0 where none)."""
    wanted = {month_key(*ym) for ym in months}
    out: dict[tuple[str, str], int | float] = {}
    for q, rows in zip(queries, rows_by_query, strict=True):
        for mk in wanted:
            out.setdefault((mk, q.stream), 0)
        for r in rows:
            if q.mode == "grain":
                if r[0] is None:
                    continue
                mk, value = bps._day(r[0])[:7], r[1]
            elif q.mode == "pair":
                if r[0] is None or r[1] is None:
                    continue
                mk, value = month_key(int(r[0]), int(r[1])), r[2]
            else:
                mk, value = month_key(*q.month), (r[0] if r else 0)
            if mk in wanted:
                out[(mk, q.stream)] = finance._number(
                    out.get((mk, q.stream), 0) + finance._number(value)
                )
    return out


def snapshot_documents(doc, payload):
    """A stream's documents in a Finance month-close snapshot, or None if absent."""
    if not payload or payload.get("error"):
        return None
    blocks = payload.get("blocks") or []
    if doc.block >= len(blocks):
        return None
    block = blocks[doc.block]
    if not doc.where:
        for f in block.get("figures") or []:
            if f.get("code") == doc.metric:
                return f.get("value")
        return None
    # A filtered count is a breakdown row of the section (Xpert's per-client table).
    wanted = {str(w["value"]) for w in doc.where if w.get("op") == "eq"}
    dims = {w["field"] for w in doc.where}
    for br in block.get("breakdowns") or []:
        if br.get("kind") != "table" or br.get("dim") not in dims:
            continue
        codes = [c.get("code") for c in br.get("columns") or []]
        if doc.metric not in codes:
            continue
        i = codes.index(doc.metric)
        for row in br.get("rows") or []:
            if row.get("key") in wanted:
                return row["values"][i]
        return 0
    return None


# --------------------------------------------------------------------------
# Rates
# --------------------------------------------------------------------------


def _as_date(value):
    if value is None or isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    return dt.date.fromisoformat(str(value).strip()[:10])


def normalize_rate(row):
    """A dbo.FinanceRates row (RateId, Kind, StreamKey, Value, ValidFrom, ValidTo,
    ChangedAt, ChangedBy) as the dict the rest of this module reads."""
    return {
        "id": int(row[0]),
        "kind": row[1],
        "stream": row[2] or None,
        "value": _dec(row[3]),
        "from": _as_date(row[4]),
        "to": _as_date(row[5]),
        "changedAt": row[6],
        "changedBy": row[7],
    }


def rate_for(rates, kind, stream_key, year, month):
    """The rate of `kind` valid for a stream in a month: the stream's own
    override if one is valid, else the default; the latest ValidFrom wins
    among overlapping rows. None when no row is valid."""
    first = dt.date(year, month, 1)

    def valid(r):
        return r["kind"] == kind and r["from"] <= first and (r["to"] is None or first <= r["to"])

    for scope in (stream_key, None) if stream_key else (None,):
        found = [r for r in rates if valid(r) and r["stream"] == scope]
        if found:
            return max(found, key=lambda r: (r["from"], r["id"]))["value"]
    return None


def check_rate(kind, stream_key, value, valid_from, valid_to):
    """Validate a rate the page submits; returns (clean values) or raises ValueError(msgid)."""
    if kind not in RATE_KINDS:
        raise ValueError(N_("Unknown rate kind."))
    if stream_key not in (None, "") and stream_key not in STREAMS_BY_KEY:
        raise ValueError(N_("Unknown stream."))
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError("not finite")
        amount = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception as e:
        raise ValueError(N_("The rate must be a number.")) from e
    if amount <= 0 or amount >= Decimal("100000000"):
        raise ValueError(N_("The rate must be a positive number."))

    def first_of(v):
        y, m = str(v or "").split("-")[:2]
        return dt.date(int(y), int(m), 1)

    try:
        start = first_of(valid_from)
        end = first_of(valid_to) if valid_to else None
    except (ValueError, TypeError) as e:
        raise ValueError(N_("A month must read YYYY-MM.")) from e
    if end is not None and end < start:
        raise ValueError(N_("'Valid to' is before 'valid from'."))
    return kind, (stream_key or None), amount, start, end


def rate_overlap(rates, kind, stream_key, start, end, ignore_id=None):
    """The first rate of the same kind and scope (default or one stream) whose
    validity overlaps start..end (None = open-ended), or None. Two rows of one
    scope must not overlap: the page edits a period, it does not stack them."""
    far = dt.date.max
    for r in sorted(rates, key=lambda r: r["from"]):
        if r["id"] == ignore_id or r["kind"] != kind or r["stream"] != (stream_key or None):
            continue
        if r["from"] <= (end or far) and start <= (r["to"] or far):
            return r
    return None


def check_cost(month, stream_key, label, amount):
    """Validate an external cost the page submits; (first of month, stream, label,
    amount) or raises ValueError(msgid)."""
    if stream_key not in STREAMS_BY_KEY:
        raise ValueError(N_("Unknown stream."))
    label = " ".join(str(label or "").split())[:200]
    if not label:
        raise ValueError(N_("Name the cost."))
    try:
        y, m = str(month or "").split("-")[:2]
        first = dt.date(int(y), int(m), 1)
    except (ValueError, TypeError) as e:
        raise ValueError(N_("A month must read YYYY-MM.")) from e
    try:
        value = Decimal(str(amount))
        if not value.is_finite():
            raise ValueError("not finite")
        value = value.quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception as e:
        raise ValueError(N_("The amount must be a number.")) from e
    if value == 0 or abs(value) >= Decimal("10000000000"):
        raise ValueError(N_("The amount must not be 0."))
    return first, stream_key, label, value


def rates_payload(rates):
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "stream": r["stream"],
            "value": float(r["value"]),
            "from": r["from"].isoformat()[:7],
            "to": r["to"].isoformat()[:7] if r["to"] else None,
            "changedAt": r["changedAt"].isoformat()
            if isinstance(r["changedAt"], dt.datetime)
            else (str(r["changedAt"]) if r["changedAt"] else None),
            "changedBy": r["changedBy"],
        }
        for r in sorted(rates, key=lambda r: (r["kind"], r["stream"] or "", r["from"], r["id"]))
    ]


# --------------------------------------------------------------------------
# Invoices
# --------------------------------------------------------------------------


def assign_invoices(invoices, project_streams, linked_contacts, overrides=None):
    """Split normalized Bexio invoices by stream.

    An invoice's stream is its override (dbo.ControllingInvoiceStreams) if it
    has one, else its project's (dbo.ControllingStreamProjects). A mapping to
    None excludes the invoice on purpose (postage, other mandants).

    Returns ({(month key, stream): [invoice]}, {month key: [invoice]}): the
    second holds the invoices to a linked Finance contact that nothing maps --
    reported as unassigned, never guessed. Invoices to anyone else are not
    this page's business. Cancelled invoices are dropped.
    """
    overrides = overrides or {}
    by: dict[tuple[str, str], list] = {}
    unassigned: dict[str, list] = {}
    for inv in sorted(invoices, key=lambda i: (i.get("date") or "", i.get("nr") or "")):
        if inv.get("status") == "cancelled":
            continue
        ym = billed_month(inv.get("date"))
        if ym is None:
            continue
        mk = month_key(*ym)
        if inv.get("id") in overrides:
            key = overrides[inv["id"]]
        elif inv.get("projectId") in project_streams:
            key = project_streams[inv["projectId"]]
        else:
            if inv.get("contactId") in linked_contacts:
                unassigned.setdefault(mk, []).append(inv)
            continue
        if key in STREAMS_BY_KEY:
            by.setdefault((mk, key), []).append(inv)
    return by, unassigned


# --------------------------------------------------------------------------
# External costs
# --------------------------------------------------------------------------


def normalize_cost(row):
    """A dbo.ControllingCosts row (CostId, Month, StreamKey, Label, Amount,
    ChangedAt, ChangedBy) as an external cost item."""
    month = _as_date(row[1])
    return {
        "id": int(row[0]),
        "month": month_key(month.year, month.month),
        "stream": row[2],
        "label": row[3],
        "amount": _dec(row[4]),
        "source": "manual",
        "changedBy": row[6],
    }


def bill_costs(bills, vendor_streams):
    """Bexio purchase bills -> external cost items, by the vendor map
    ({lowercase match: (stream, label)}), in the month of their bill date.
    Drafts are skipped; a bill in another currency has no amount (flagged)."""
    out = []
    for b in bills:
        if b.get("status") == "draft" or not b.get("date"):
            continue
        vendor = (b.get("vendor") or "").casefold()
        hit = next(((s, label) for m, (s, label) in vendor_streams.items() if m in vendor), None)
        if hit is None or hit[0] not in STREAMS_BY_KEY:
            continue
        home = (b.get("currency") or HOME_CURRENCY) == HOME_CURRENCY
        out.append(
            {
                "id": b.get("id"),
                "month": b["date"][:7],
                "stream": hit[0],
                "label": f"{hit[1]} · {b.get('title') or b.get('nr')}",
                "amount": _dec(b["net"]) if home else None,
                "source": "bexio",
                "ref": b.get("nr"),
            }
        )
    return out


def fold_costs(items):
    """{(month key, stream): [item]} of manual and Bexio cost items."""
    out: dict[tuple[str, str], list] = {}
    for item in items:
        out.setdefault((item["month"], item["stream"]), []).append(item)
    return out


def _is_home(inv):
    # A blank code means Bexio's currency list could not be read: Sydoc bills in CHF.
    return (inv.get("currency") or HOME_CURRENCY) == HOME_CURRENCY


def _sums(invoices):
    """(excl, incl) of invoices, Decimal."""
    excl = sum((_dec(i["excl"]) for i in invoices), Decimal(0))
    incl = sum((_dec(i["total"]) for i in invoices), Decimal(0))
    return excl, incl


def invoice_state(invoices, linked):
    """(state, excl, incl) of a stream month's invoices.

    excl/incl are the CHF totals of the issued invoices (Decimal), None
    unless the state is INVOICED. An issued invoice in another currency makes
    the month FOREIGN: its amount cannot be added up honestly.
    """
    if not linked:
        return UNLINKED, None, None
    issued = [i for i in invoices if bexio.counts(i)]
    if issued:
        if any(not _is_home(i) for i in issued):
            return FOREIGN, None, None
        excl, incl = _sums(issued)
        return INVOICED, excl, incl
    if any(i.get("status") == "draft" for i in invoices):
        return DRAFT, None, None
    return MISSING, None, None


def foreign_totals(invoices):
    """[{currency, excl, total}] of the issued foreign-currency invoices."""
    by: dict[str, list] = {}
    for i in invoices:
        if bexio.counts(i) and not _is_home(i):
            by.setdefault(i["currency"], []).append(i)
    return [
        {"currency": c, "excl": _money(_sums(v)[0]), "total": _money(_sums(v)[1])}
        for c, v in sorted(by.items())
    ]


def draft_totals(invoices):
    """(excl, incl) of the draft invoices in CHF, or (None, None) without one."""
    drafts = [i for i in invoices if i.get("status") == "draft" and _is_home(i)]
    if not drafts:
        return None, None
    return _sums(drafts)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def _money(value):
    return None if value is None else float(_dec(value).quantize(CENT, rounding=ROUND_HALF_UP))


def _hours(value):
    return None if value is None else float(_dec(value).quantize(CENT, rounding=ROUND_HALF_UP))


def _ratio(num, den, places=4):
    if num is None or den in (None, 0) or not _dec(den):
        return None
    q = Decimal(1).scaleb(-places)
    return float((_dec(num) / _dec(den)).quantize(q, rounding=ROUND_HALF_UP))


@dataclass
class Inputs:
    """Everything the payload builders read, already fetched by the view."""

    hours: Hours
    rates: list
    documents: dict  # {(month key, stream): value} -- snapshot where closed, else live
    documents_live: dict = field(default_factory=dict)  # live, where a snapshot was used
    invoices: dict | None = None  # assign_invoices()[0]; None = Bexio could not be read
    unassigned: dict = field(default_factory=dict)
    linked_streams: frozenset = frozenset()  # streams with at least one mapped project
    bexio_error: str | None = None
    costs: dict = field(default_factory=dict)  # fold_costs(); external costs per stream month
    costs_error: str | None = None  # the Bexio bills could not be read
    hours_error: str | None = None  # BPS could not be read: hours unknown, not 0
    frozen: dict = field(default_factory=dict)  # {month key: snapshot()} of closed months
    contacts: dict = field(default_factory=dict)  # {Bexio contact id: name}


def stream_month(stream, year, month, inp, translate=lambda s: s):
    """One stream in one month: hours, cost, invoiced, margin, documents, KPIs.

    A closed month answers with its snapshot (the figures it was closed with)
    and keeps the live invoices next to it: their lines, and -- when Bexio
    now differs from the close -- the live amount (`live`, flag `moved`)."""
    mk = month_key(year, month)
    live = _live_cell(stream, year, month, inp, translate)
    snap = (inp.frozen.get(mk) or {}).get("streams", {}).get(stream.key)
    if snap is None:
        return live
    # Defaults first: a snapshot written by an older release may lack a key.
    cell = {
        **{k: None for k in SNAPSHOT_KEYS},
        "tasks": {},
        "foreign": [],
        "externalCosts": [],
        "contacts": [],
        "flags": [],
        "kpis": {},
        **snap,
    }
    cell["frozen"] = True
    cell["invoices"] = live["invoices"]
    cell["contacts"] = live["contacts"] or snap.get("contacts") or []
    note = incomplete_note(stream.key, year, month)
    cell["incomplete"] = translate(note) if note else None
    flags = [f for f in snap.get("flags") or [] if f != "moved"]
    if live["state"] != ERROR and (
        live["state"] != snap.get("state") or live["invoiced"] != snap.get("invoiced")
    ):
        flags.append("moved")
        cell["live"] = {k: live[k] for k in ("state", "invoiced", "invoicedIncl", "foreign")}
    cell["flags"] = flags
    return cell


def _live_cell(stream, year, month, inp, translate):
    mk = month_key(year, month)
    tasks = {} if inp.hours_error else inp.hours.tasks(mk, stream.key)
    hours = None if inp.hours_error else sum(tasks.values(), Decimal(0))
    rate = rate_for(inp.rates, HOURLY, stream.key, year, month)
    default = rate_for(inp.rates, HOURLY, None, year, month)
    hours_cost = (
        (hours * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        if rate is not None and hours is not None
        else None
    )
    externals = inp.costs.get((mk, stream.key), [])
    external = sum((_dec(c["amount"]) for c in externals if c["amount"] is not None), Decimal(0))
    unknown_cost = any(c["amount"] is None for c in externals)
    cost = hours_cost + external if hours_cost is not None and not unknown_cost else None
    if inp.invoices is None:
        state, excl, incl, invoices = ERROR, None, None, []
    else:
        invoices = inp.invoices.get((mk, stream.key), [])
        state, excl, incl = invoice_state(invoices, stream.key in inp.linked_streams)
    draft_excl, draft_incl = draft_totals(invoices) if state == DRAFT else (None, None)
    margin = excl - cost if excl is not None and cost is not None else None
    docs = inp.documents.get((mk, stream.key)) if stream.documents else None
    docs_live = inp.documents_live.get((mk, stream.key))
    validation = tasks.get(VALIDATION_TASK, Decimal(0))
    flags = []
    if inp.hours_error:
        flags.append("bps_error")
    if rate is None:
        flags.append("no_rate")
    elif default is not None and rate != default:
        flags.append("override")
    if unknown_cost:
        flags.append("cost_unknown")
    if hours is not None and not hours and state in (INVOICED, DRAFT):
        # Invoiced work with no hour booked: a 100 % margin would mislead.
        flags.append("no_hours")
    note = incomplete_note(stream.key, year, month)
    if note:
        flags.append("incomplete")
    contacts = sorted({inp.contacts.get(i.get("contactId")) for i in invoices} - {None})
    return {
        "month": mk,
        "hours": _hours(hours),
        "tasks": {t: _hours(h) for t, h in sorted(tasks.items(), key=lambda kv: (-kv[1], kv[0]))},
        "rate": _money(rate),
        "hoursCost": _money(hours_cost),
        "externalCosts": [
            {k: (_money(v) if k == "amount" else v) for k, v in c.items() if k != "changedBy"}
            for c in externals
        ],
        "cost": _money(cost),
        "state": state,
        "invoiced": _money(excl),
        "invoicedIncl": _money(incl),
        "draft": _money(draft_excl),
        "draftIncl": _money(draft_incl),
        "foreign": foreign_totals(invoices),
        "margin": _money(margin),
        "marginPct": _ratio(margin, excl),
        "documents": docs,
        "documentsLive": docs_live if docs_live is not None and docs_live != docs else None,
        "kpis": {
            "secondsPerDocument": _ratio(validation * 3600, docs, 1) if validation else None,
            "documentsPerHour": _ratio(docs, hours, 2) if hours else None,
            "chfPerDocument": _ratio(excl, docs, 4),
        },
        "validationHours": _hours(validation) if hours is not None else None,
        "invoices": [_invoice_brief(i) for i in invoices],
        "contacts": contacts,
        "flags": flags,
        "incomplete": translate(note) if note else None,
    }


#: What a month-close snapshot keeps of a stream month (the invoices stay live).
SNAPSHOT_KEYS = (
    "month",
    "hours",
    "tasks",
    "rate",
    "hoursCost",
    "externalCosts",
    "cost",
    "state",
    "invoiced",
    "invoicedIncl",
    "draft",
    "draftIncl",
    "foreign",
    "margin",
    "marginPct",
    "documents",
    "kpis",
    "validationHours",
    "contacts",
    "flags",
)


def snapshot(year, month, inp):
    """The Controlling figures of a month as Finance's close freezes them:
    every stream's cell without its invoice list (Bexio stays live) and the
    unassigned invoices. JSON-ready."""
    mk = month_key(year, month)
    streams = {}
    for s in STREAMS:
        cell = _live_cell(s, year, month, inp, lambda m: m)
        streams[s.key] = {k: cell[k] for k in SNAPSHOT_KEYS}
        streams[s.key]["invoiceIds"] = [i["id"] for i in cell["invoices"]]
    return {
        "month": mk,
        "streams": streams,
        "unassigned": [_invoice_brief(i) for i in inp.unassigned.get(mk, [])],
    }


def snapshot_problems(snap):
    """Why a snapshot should not be taken: the sources that were down."""
    out = []
    for cell in snap["streams"].values():
        if "bps_error" in cell["flags"]:
            out.append("BPS")
        if cell["state"] == ERROR:
            out.append("Bexio")
    return sorted(set(out))


def _invoice_brief(inv):
    keep = (
        "id",
        "nr",
        "title",
        "date",
        "status",
        "total",
        "excl",
        "currency",
        "projectId",
        "contactId",
    )
    out = {k: inv.get(k) for k in keep}
    if inv.get("projectName"):
        out["projectName"] = inv["projectName"]
    return out


def _sum(cells, key):
    values = [c[key] for c in cells if c.get(key) is not None]
    return _money(sum((_dec(v) for v in values), Decimal(0))) if values else None


def totals(cells, year, month, rates):
    """The month's total row. Invoiced and margin add up the streams that have
    them, and say how many streams were left out (flagged) so a total is never
    read as complete when it is not."""
    with_margin = [c for c in cells if c["margin"] is not None]
    invoiced = _sum(with_margin, "invoiced")
    margin = _sum(with_margin, "margin")
    hours = _sum(cells, "hours")
    day_hours = rate_for(rates, FTE_DAY_HOURS, None, year, month)
    capacity = day_hours * working_days(year, month) if day_hours else None
    return {
        "hours": hours,
        "cost": _sum(cells, "cost"),
        "invoiced": _sum([c for c in cells if c["invoiced"] is not None], "invoiced"),
        "invoicedIncl": _sum([c for c in cells if c["invoicedIncl"] is not None], "invoicedIncl"),
        "margin": margin,
        "marginPct": _ratio(margin, invoiced),
        "documents": _sum([c for c in cells if c["documents"] is not None], "documents"),
        "streams": len(cells),
        "streamsWithMargin": len(with_margin),
        "fte": _ratio(hours, capacity, 2) if capacity and hours is not None else None,
        "fteCapacity": _hours(capacity),
        "workingDays": working_days(year, month),
    }


def task_matrix(cells_by_stream):
    """Hours by task x stream with row and column totals, tasks by total hours."""
    keys = list(cells_by_stream)
    by_task: dict[str, dict[str, Decimal]] = {}
    for key, cell in cells_by_stream.items():
        for task, h in cell["tasks"].items():
            by_task.setdefault(task, {})[key] = _dec(h)
    row_tot = {t: sum(v.values(), Decimal(0)) for t, v in by_task.items()}
    tasks = sorted(by_task, key=lambda t: (-row_tot[t], t.casefold()))
    col_tot = {k: sum((by_task[t].get(k, Decimal(0)) for t in tasks), Decimal(0)) for k in keys}
    return {
        "tasks": tasks,
        "streams": keys,
        "cells": [
            [_hours(by_task[t].get(k)) if k in by_task[t] else None for k in keys] for t in tasks
        ],
        "taskTotals": [_hours(row_tot[t]) for t in tasks],
        "streamTotals": [_hours(col_tot[k]) for k in keys],
        "total": _hours(sum(row_tot.values(), Decimal(0))),
    }


def unmapped_payload(hours, mkey):
    rows = hours.unmapped.get(mkey, {})
    return [
        {"customer": c, "package": p, "task": t, "hours": _hours(h)}
        for (c, p, t), h in sorted(rows.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def month_payload(year, month, inp, translate=lambda s: s, positions=None):
    """The page payload of one month and its comparison with the month before."""
    prev = shift_month(year, month, -1)
    positions = positions or {}
    streams, cur_cells, prev_cells = [], {}, {}
    for s in STREAMS:
        cur = stream_month(s, year, month, inp, translate)
        before = stream_month(s, prev[0], prev[1], inp, translate) if prev >= EARLIEST else None
        for inv in cur["invoices"]:
            if inv["id"] in positions:
                inv["positions"] = positions[inv["id"]]
        cur_cells[s.key] = cur
        if before is not None:
            prev_cells[s.key] = before
        streams.append(
            {
                **stream_descriptor(s, translate),
                "cur": cur,
                "prev": before,
                "delta": _delta(cur, before),
            }
        )
    mk = month_key(year, month)
    pk = month_key(*prev)
    return {
        "month": mk,
        "prevMonth": pk if prev >= EARLIEST else None,
        "streams": streams,
        "totals": {
            "cur": totals(list(cur_cells.values()), year, month, inp.rates),
            "prev": totals(list(prev_cells.values()), prev[0], prev[1], inp.rates)
            if prev_cells
            else None,
        },
        "tasks": None if inp.hours_error and mk not in inp.frozen else task_matrix(cur_cells),
        "unassigned": [_invoice_brief(i) for i in inp.unassigned.get(mk, [])],
        "unmapped": [] if inp.hours_error else unmapped_payload(inp.hours, mk),
        "bexioError": inp.bexio_error,
        "hoursError": inp.hours_error,
    }


def stream_descriptor(s, translate=lambda m: m):
    """The static part of a stream the page renders before any data."""
    return {
        "key": s.key,
        "label": s.label,
        "client": s.client,
        "title": translate(s.title) if s.title else None,
        "nav": s.nav or s.label,
        "unit": translate(s.unit),
        "bps": " · ".join(c + (f" › {p}" if p else "") for c, p in s.hours),  # noqa: RUF001
    }


def _delta(cur, prev):
    if prev is None:
        return None

    def d(key):
        a, b = cur.get(key), prev.get(key)
        return None if a is None or b is None else _money(_dec(a) - _dec(b))

    return {k: d(k) for k in ("hours", "cost", "invoiced", "margin", "documents")}


def trend_payload(months, inp, translate=lambda s: s):
    """Per stream and month: hours, cost, invoiced, margin, documents and state,
    plus the monthly totals -- the series of the trend chart."""
    series: list[dict] = []
    for s in STREAMS:
        points = []
        for y, m in months:
            c = stream_month(s, y, m, inp, translate)
            points.append(
                {
                    k: c[k]
                    for k in (
                        "month",
                        "hours",
                        "cost",
                        "invoiced",
                        "margin",
                        "marginPct",
                        "documents",
                        "state",
                        "flags",
                    )
                }
            )
        series.append({"key": s.key, "label": s.label, "nav": s.nav or s.label, "points": points})
    month_totals = []
    for i, (y, m) in enumerate(months):
        cells: list[dict] = [dict(sr["points"][i], invoicedIncl=None, tasks={}) for sr in series]
        t = totals(cells, y, m, inp.rates)
        t["month"] = month_key(y, m)
        month_totals.append(t)
    return {
        "months": [month_key(y, m) for y, m in months],
        "streams": series,
        "totals": month_totals,
    }
