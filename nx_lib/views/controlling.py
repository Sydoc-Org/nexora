"""Sydoc Controlling (#433): margin per client stream -- BPS hours x rate against Bexio.

The page is a shell that knows the month; /api/controlling/month returns the
whole month (summary, per-stream detail with invoice lines, hours by task,
volumes) and /api/controlling/trend the series since January 2025. The rules
live in nx_lib/controlling.py; this module fetches the four inputs and runs
them:

* BPS hours through the registered ``bps_projects`` source (the BPS page's
  loader and query builder);
* the rates of dbo.FinanceRates and the stream <-> Bexio project map of
  dbo.ControllingStreamProjects (0145);
* the Bexio invoices, live (nx_lib/bexio.py, cached for five minutes);
* the documents per stream through the Finance sections' registered sources,
  or from the Finance month-close snapshot when the month is closed -- the
  live count rides along where it moved since.

controlling.view is the whole gate (0145); rates are edited by
finance.month.edit holders, the code that closes a Finance month.
"""

import datetime as dt
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Response, current_app, jsonify, render_template, request, session
from flask_babel import format_date, get_locale, gettext

from .. import bexio, controlling, controlling_export
from ..controlling import EARLIEST, STREAMS, Inputs, month_key, shift_month
from ..db import engine_nexora_db
from ..extensions import limiter
from ..reporting.semantic import MetricResolveError
from ..reporting.table_query import TableQueryError, table_source_catalog
from ..security import has_permission, page_visibility, require_permission
from .bps import _source as _bps_source
from .finance import _closed_months_safe
from .finance_bexio import _links, _message
from .reporting._shared import (
    _CURATED_ENGINES,
    _execute,
    _get_effective_source,
    _metrics_for_source,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
POSITION_WORKERS = 6
#: The trend reads ~20 months of every source (~10 s); it is cached this long
#: per process (?fresh=1 bypasses it, a rate or cost change clears it).
TREND_TTL = 300
_trend_cache: dict = {}
_trend_lock = threading.Lock()


def _month_label(year, month):
    return format_date(dt.date(year, month, 1), "LLLL yyyy")


def _actor():
    return (session.get("fullname") or session.get("username") or "?")[:100]


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


class SourceError(Exception):
    """An input could not be read; str(e) is safe to show."""

    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail


def _detail(exc):
    text = str(exc).strip().splitlines()
    return text[0][:200] if text else None


def _nexora_rows(sql, params=()):
    if engine_nexora_db is None:
        raise SourceError(gettext("The nexora database is not configured."))
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def _rates():
    rows = _nexora_rows(
        "SELECT RateId, Kind, StreamKey, Value, ValidFrom, ValidTo, ChangedAt, ChangedBy "
        "FROM dbo.FinanceRates"
    )
    return [controlling.normalize_rate(r) for r in rows]


def _project_streams():
    """{Bexio project id: stream key, or None for a project excluded on purpose}."""
    rows = _nexora_rows("SELECT ProjectId, StreamKey FROM dbo.ControllingStreamProjects")
    return {int(r[0]): (str(r[1]) if r[1] else None) for r in rows}


def _invoice_overrides():
    """{Bexio invoice id: stream key or None} -- beats the invoice's project (0146)."""
    rows = _nexora_rows("SELECT InvoiceId, StreamKey FROM dbo.ControllingInvoiceStreams")
    return {int(r[0]): (str(r[1]) if r[1] else None) for r in rows}


def _manual_costs(months):
    (fy, fm), (ly, lm) = min(months), max(months)
    first = dt.date(fy, fm, 1).isoformat()
    last = dt.date(ly, lm, 1).isoformat()
    rows = _nexora_rows(
        "SELECT CostId, Month, StreamKey, Label, Amount, ChangedAt, ChangedBy "
        "FROM dbo.ControllingCosts WHERE Month >= ? AND Month <= ?",
        (first, last),
    )
    return [controlling.normalize_cost(r) for r in rows]


def _bill_costs(months, fresh=False):
    """(external cost items from Bexio purchase bills, error message or None)."""
    vendors = {
        str(r[0]).casefold(): (str(r[1]), str(r[2]))
        for r in _nexora_rows("SELECT Match, StreamKey, Label FROM dbo.ControllingVendorStreams")
    }
    if not vendors or not bexio.configured():
        return [], None
    try:
        bills = [bexio.normalize_bill(b) for b in bexio.purchase_bills(fresh=fresh)]
    except bexio.BexioError as e:
        current_app.logger.warning(f"controlling: Bexio purchase bills unreadable: {e}")
        return [], _message(e)
    wanted = {month_key(*ym) for ym in months}
    return [c for c in controlling.bill_costs(bills, vendors) if c["month"] in wanted], None


def _hours(months):
    try:
        base_object, catalog, engine, _label = _bps_source()
        sql, params = controlling.hours_query(base_object, catalog, min(months), max(months))
    except LookupError as e:
        raise SourceError(str(e)) from e
    except (controlling.ControllingSpecError, TableQueryError, ValueError) as e:
        current_app.logger.warning(f"controlling: BPS source is misconfigured: {e}")
        raise SourceError(gettext("The BPS source does not match this page."), str(e)) from e
    try:
        return controlling.fold_hours(_execute(engine, sql, params))
    except Exception as e:
        current_app.logger.warning(f"controlling: BPS hours query failed: {e}")
        raise SourceError(gettext("Could not read the BPS hours."), _detail(e)) from e


def _live_documents(months):
    """{(month key, stream): count} read live; streams whose source fails are left out
    (logged) -- their documents show as unknown, the rest of the page still renders."""
    out, failed = {}, []
    cache = {}
    for stream in STREAMS:
        doc = stream.documents
        if doc is None:
            continue
        code = doc.finance_section.source
        try:
            if code not in cache:
                source = _get_effective_source(code)
                if (
                    source is None
                    or source.get("provider") != "table"
                    or not source.get("baseObject")
                ):
                    raise SourceError(
                        gettext("The reporting source %(code)s is not registered.", code=code)
                    )
                engine = _CURATED_ENGINES.get(source.get("engine"))
                if engine is None:
                    raise SourceError(gettext("The source's database is not configured."))
                cache[code] = (
                    source["baseObject"],
                    table_source_catalog(source.get("columns")),
                    _metrics_for_source(source["id"], get_locale()),
                    engine,
                )
            base_object, catalog, metrics, engine = cache[code]
            queries = controlling.documents_queries(stream, base_object, catalog, metrics, months)
            rows = [_execute(engine, q.sql, q.params) for q in queries]
            out.update(controlling.fold_documents(queries, rows, months))
        except (
            SourceError,
            controlling.ControllingSpecError,
            MetricResolveError,
            TableQueryError,
        ) as e:
            current_app.logger.warning(f"controlling: documents of {stream.key} unavailable: {e}")
            failed.append(stream.key)
        except Exception as e:
            current_app.logger.warning(f"controlling: documents query of {stream.key} failed: {e}")
            failed.append(stream.key)
    return out, failed


def _snapshots(month_keys):
    """{month key: {finance section key: payload}} of the closed months asked for,
    only the sections a stream counts its documents with."""
    keys = sorted({s.documents.section for s in STREAMS if s.documents})
    wanted = sorted(set(month_keys) & _closed_months_safe())
    if not wanted:
        return {}
    marks_m = ",".join("?" * len(wanted))
    marks_s = ",".join("?" * len(keys))
    try:
        rows = _nexora_rows(
            "SELECT Month, SectionKey, Payload FROM dbo.FinanceMonthClose "
            f"WHERE Month IN ({marks_m}) AND SectionKey IN ({marks_s})",
            (*wanted, *keys),
        )
    except Exception as e:
        current_app.logger.warning(f"controlling: could not read the Finance snapshots: {e}")
        return {}
    out: dict = {}
    for month, section, payload in rows:
        try:
            out.setdefault(str(month), {})[str(section)] = json.loads(payload)
        except ValueError:
            continue
    return out


def _documents(months):
    """(documents, live where it moved, closed month keys, streams that failed).

    A closed month counts what its Finance snapshot counted -- the figures it
    was invoiced on -- and keeps the live count next to it."""
    live, failed = _live_documents(months)
    snaps = _snapshots([month_key(*ym) for ym in months])
    docs = dict(live)
    moved = {}
    for mk, sections in snaps.items():
        for stream in STREAMS:
            if stream.documents is None:
                continue
            value = controlling.snapshot_documents(
                stream.documents, sections.get(stream.documents.section)
            )
            if value is None:
                continue
            key = (mk, stream.key)
            if key in live:
                moved[key] = live[key]
            docs[key] = value
    return docs, moved, set(snaps), failed


def _invoices(months, fresh=False):
    """(normalized invoices of the windows billing `months`, error message or None)."""
    if not bexio.configured():
        return None, gettext("Bexio is not configured on this server (BEXIO_PAT).")
    first = bexio.invoice_window(*min(months))[0]
    last = bexio.invoice_window(*max(months))[1]
    try:
        raw = bexio.search_invoices(first, last, fresh=fresh)
        codes = bexio.currencies()
    except bexio.BexioError as e:
        current_app.logger.warning(f"controlling: Bexio read {first}..{last} failed: {e}")
        return None, _message(e)
    invoices = [bexio.normalize_invoice(r, codes) for r in raw]
    for inv in invoices:
        if inv["currency"] and inv["currency"] != controlling.HOME_CURRENCY and inv["date"]:
            inv["fx"] = _fx(inv["currencyId"], inv["date"])
    return invoices, None


def _fx(currency_id, date):
    """Bexio's CHF rate for a foreign invoice's month; None (logged) when it has none."""
    if currency_id is None:
        return None
    try:
        return bexio.exchange_rate(currency_id, date)
    except bexio.BexioError as e:
        current_app.logger.warning(
            f"controlling: no Bexio rate for currency {currency_id} {date}: {e}"
        )
        return None


def _inputs(months, fresh=False):
    """Inputs for `months`; raises SourceError when BPS or the rates cannot be read
    (without them there is no page). Bexio and documents degrade per stream."""
    hours = _hours(months)
    try:
        rates = _rates()
        projects = _project_streams()
        overrides = _invoice_overrides()
        manual = _manual_costs(months)
    except Exception as e:
        current_app.logger.warning(f"controlling: rates/projects/costs unreadable: {e}")
        raise SourceError(gettext("Could not read the rates."), _detail(e)) from e
    try:
        bills, costs_error = _bill_costs(months, fresh)
    except Exception as e:
        current_app.logger.warning(f"controlling: vendor map unreadable: {e}")
        bills, costs_error = [], gettext("Could not read the external costs.")
    docs, moved, closed, failed = _documents(months)
    invoices, error = _invoices(months, fresh)
    by, unassigned = ({}, {})
    if invoices is not None:
        linked = {link.contact_id for link in _links()}
        by, unassigned = controlling.assign_invoices(invoices, projects, linked, overrides)
    inp = Inputs(
        hours=hours,
        rates=rates,
        documents=docs,
        documents_live=moved,
        invoices=by if invoices is not None else None,
        unassigned=unassigned,
        linked_streams=frozenset(k for k in (*projects.values(), *overrides.values()) if k),
        bexio_error=error,
        costs=controlling.fold_costs(manual + bills),
        costs_error=costs_error,
    )
    return inp, closed, failed


def _positions(invoices):
    """{invoice id: lines} of the given invoices, read in parallel; an invoice
    whose lines cannot be read is left out (its block offers the PDF instead)."""
    ids = sorted({i["id"] for i in invoices})
    if not ids:
        return {}

    def one(invoice_id):
        try:
            return invoice_id, bexio.normalize_positions(bexio.invoice(invoice_id).get("positions"))
        except bexio.BexioError:
            return invoice_id, None

    with ThreadPoolExecutor(max_workers=min(POSITION_WORKERS, len(ids))) as pool:
        return {i: lines for i, lines in pool.map(one, ids) if lines is not None}


def _month_from_request():
    year, month = controlling.parse_month(request.args.get("month"))
    return year, month


def _build_month(year, month, fresh=False, with_positions=True):
    months = [ym for ym in (shift_month(year, month, -1), (year, month)) if ym >= EARLIEST]
    inp, closed, failed = _inputs(months, fresh)
    mk = month_key(year, month)
    positions = {}
    if with_positions and inp.invoices is not None:
        current = [i for (m, _k), invs in inp.invoices.items() if m == mk for i in invs]
        current += inp.unassigned.get(mk, [])
        positions = _positions(current)
    payload = controlling.month_payload(year, month, inp, gettext, positions)
    today = dt.date.today()
    payload.update(
        label=_month_label(year, month),
        state="running"
        if (year, month) == (today.year, today.month)
        else ("closed" if mk in closed else "open"),
        documentsFailed=failed,
        costsError=inp.costs_error,
        window=dict(
            zip(("from", "to"), bexio.invoice_window(year, month)[:2], strict=True),
            label=_month_label(*bexio.invoice_window(year, month)[2]),
        ),
        error=None,
    )
    return payload


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@require_permission("controlling.view")
def controlling_page():
    today = dt.date.today()
    year, month = _month_from_request()
    is_current = (year, month) == (today.year, today.month)
    prev = shift_month(year, month, -1)
    nxt = shift_month(year, month, 1)
    closed = _closed_months_safe()
    months = []
    ym = (today.year, today.month)
    while ym >= EARLIEST:
        key = month_key(*ym)
        state = (
            "running"
            if ym == (today.year, today.month)
            else ("closed" if key in closed else "open")
        )
        months.append({"value": key, "label": _month_label(*ym), "state": state})
        ym = shift_month(*ym, -1)
    return render_template(
        "controlling.html",
        page_visibility=page_visibility(),
        month=month_key(year, month),
        month_label=_month_label(year, month),
        month_name=format_date(dt.date(year, month, 1), "LLLL"),
        month_year=str(year),
        prev_month=month_key(*prev) if prev >= EARLIEST else None,
        next_month=None if is_current else month_key(*nxt),
        is_current_month=is_current,
        months=months,
        streams=[{"key": s.key, "label": s.label, "client": s.client} for s in STREAMS],
        can_edit_rates=has_permission("finance.month.edit"),
        can_finance=has_permission("finance.view"),
        can_bps=has_permission("bps.view"),
    )


def _error(e, status=200):
    # A source that is down is answered in place (200 + error), like Finance/BPS.
    return jsonify({"error": str(e), "detail": getattr(e, "detail", None)}), status


@require_permission("controlling.view")
@limiter.limit("60 per minute")
def api_controlling_month():
    year, month = _month_from_request()
    try:
        payload = _build_month(year, month, fresh=request.args.get("fresh") == "1")
    except SourceError as e:
        return _error(e)
    return jsonify(payload)


@require_permission("controlling.view")
@limiter.limit("30 per minute")
def api_controlling_trend():
    """Every month from January 2025 up to ?month (default: the previous month)."""
    year, month = _month_from_request()
    fresh = request.args.get("fresh") == "1"
    key = (month_key(year, month), str(get_locale()))
    now = time.monotonic()
    with _trend_lock:
        hit = _trend_cache.get(key)
    if hit and hit[0] > now and not fresh:
        return jsonify(hit[1])
    months = controlling.months_between(EARLIEST, (year, month))
    try:
        inp, closed, _failed = _inputs(months, fresh=fresh)
    except SourceError as e:
        return _error(e)
    payload = controlling.trend_payload(months, inp, gettext)
    payload["closed"] = sorted(closed)
    payload["bexioError"] = inp.bexio_error
    payload["error"] = None
    if not inp.bexio_error and not inp.costs_error:
        with _trend_lock:
            _trend_cache[key] = (now + TREND_TTL, payload)
            while len(_trend_cache) > 16:
                _trend_cache.pop(next(iter(_trend_cache)))
    return jsonify(payload)


def clear_trend_cache():
    """Drop the cached trends (a rate or a cost changed)."""
    with _trend_lock:
        _trend_cache.clear()


@require_permission("controlling.view")
@limiter.limit("60 per minute")
def api_controlling_rates():
    try:
        rates = _rates()
    except Exception as e:
        current_app.logger.warning(f"controlling: rates unreadable: {e}")
        return jsonify({"error": gettext("Could not read the rates.")}), 503
    return jsonify(
        {
            "rates": controlling.rates_payload(rates),
            "streams": [{"key": s.key, "label": s.label} for s in STREAMS],
            "kinds": list(controlling.RATE_KINDS),
            "canEdit": has_permission("finance.month.edit"),
        }
    )


@require_permission("finance.month.edit")
@limiter.limit("20 per minute")
def api_controlling_rate_add():
    body = request.get_json(silent=True) or {}
    try:
        kind, stream, value, start, end = controlling.check_rate(
            body.get("kind"),
            body.get("stream"),
            body.get("value"),
            body.get("from"),
            body.get("to"),
        )
    except ValueError as e:
        return jsonify({"error": gettext(str(e))}), 400
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            # ISO strings, not dates: the legacy ODBC driver cannot bind a date (HYC00).
            cur.execute(
                "INSERT INTO dbo.FinanceRates (Kind, StreamKey, Value, ValidFrom, ValidTo, ChangedBy) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    kind,
                    stream,
                    str(value),
                    start.isoformat(),
                    end.isoformat() if end else None,
                    _actor(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"controlling: adding a rate failed: {e}")
        return jsonify({"error": gettext("Could not save the rate.")}), 500
    clear_trend_cache()
    current_app.logger.info(
        f"controlling: rate {kind} {stream or 'default'} {value} from {start} added by {_actor()}"
    )
    return jsonify({"ok": True})


@require_permission("finance.month.edit")
@limiter.limit("20 per minute")
def api_controlling_rate_delete(rate_id):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM dbo.FinanceRates WHERE RateId = ?", (int(rate_id),))
            affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"controlling: deleting rate {rate_id} failed: {e}")
        return jsonify({"error": gettext("Could not delete the rate.")}), 500
    if not affected:
        return jsonify({"error": gettext("No such rate.")}), 404
    clear_trend_cache()
    current_app.logger.info(f"controlling: rate {rate_id} deleted by {_actor()}")
    return jsonify({"ok": True})


@require_permission("finance.month.edit")
@limiter.limit("20 per minute")
def api_controlling_cost_add():
    """An external cost of a stream month (e.g. a supplier billed outside Bexio)."""
    body = request.get_json(silent=True) or {}
    try:
        month, stream, label, amount = controlling.check_cost(
            body.get("month"), body.get("stream"), body.get("label"), body.get("amount")
        )
    except ValueError as e:
        return jsonify({"error": gettext(str(e))}), 400
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dbo.ControllingCosts (Month, StreamKey, Label, Amount, ChangedBy) "
                "VALUES (?, ?, ?, ?, ?)",
                (month.isoformat(), stream, label, str(amount), _actor()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"controlling: adding a cost failed: {e}")
        return jsonify({"error": gettext("Could not save the cost.")}), 500
    clear_trend_cache()
    current_app.logger.info(f"controlling: cost {stream} {month} {amount} added by {_actor()}")
    return jsonify({"ok": True})


@require_permission("finance.month.edit")
@limiter.limit("20 per minute")
def api_controlling_cost_delete(cost_id):
    try:
        conn = engine_nexora_db.raw_connection()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM dbo.ControllingCosts WHERE CostId = ?", (int(cost_id),))
            affected = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        current_app.logger.error(f"controlling: deleting cost {cost_id} failed: {e}")
        return jsonify({"error": gettext("Could not delete the cost.")}), 500
    if not affected:
        return jsonify({"error": gettext("No such cost.")}), 404
    clear_trend_cache()
    current_app.logger.info(f"controlling: cost {cost_id} deleted by {_actor()}")
    return jsonify({"ok": True})


@require_permission("controlling.view")
@limiter.limit("20 per minute")
def api_controlling_export():
    """The whole month as .xlsx: overview, per-stream detail, hours by task, volumes."""
    year, month = _month_from_request()
    try:
        payload = _build_month(year, month)
    except SourceError as e:
        return Response(str(e), status=503, mimetype="text/plain")
    body = controlling_export.workbook(payload, _export_labels(), _month_label(year, month))
    key = month_key(year, month)
    suffix = "-closed" if payload["state"] == "closed" else ""
    return Response(
        body,
        mimetype=XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="sydoc-controlling-{key}{suffix}.xlsx"',
            # Private accounting data: never cache (tests/unit/test_static_v_lint.py).
            "Cache-Control": "no-store",
        },
    )


def _export_labels():
    return {
        "title": gettext("Sydoc Controlling"),
        "overview": gettext("Overview"),
        "detail": gettext("Detail"),
        "tasks": gettext("Hours by task"),
        "volumes": gettext("Volumes"),
        "stream": gettext("Client"),
        "task": gettext("Task"),
        "hours": gettext("Hours"),
        "rate": gettext("Rate CHF/h"),
        "cost": gettext("Cost CHF"),
        "invoiced": gettext("Invoiced excl. VAT"),
        "invoiced_incl": gettext("Invoiced incl. VAT"),
        "margin": gettext("Margin CHF"),
        "margin_pct": gettext("Margin %"),
        "delta_margin": gettext("Δ margin vs previous month"),
        "documents": gettext("Documents"),
        "previous": gettext("Previous month"),
        "state": gettext("Status"),
        "total": gettext("Total"),
        "invoice": gettext("Invoice"),
        "date": gettext("Date"),
        "position": gettext("Position"),
        "quantity": gettext("Quantity"),
        "unit_price": gettext("Unit price"),
        "amount": gettext("Amount"),
        "seconds_per_doc": gettext("Seconds per document (Validierung)"),
        "docs_per_hour": gettext("Documents per hour"),
        "chf_per_doc": gettext("Invoiced CHF per document"),
        "fte": gettext("FTE"),
        "unassigned": gettext("Unassigned invoices"),
        "unmapped": gettext("Hours on no stream"),
        "external": gettext("External cost"),
        "converted": gettext("converted to CHF"),
        "no_hours": gettext("no hours booked"),
        "cost_unknown": gettext("external cost in a foreign currency"),
        "states": {
            controlling.INVOICED: gettext("invoiced"),
            controlling.DRAFT: gettext("draft only"),
            controlling.MISSING: gettext("no invoice"),
            controlling.UNLINKED: gettext("not linked"),
            controlling.FOREIGN: gettext("foreign currency"),
            controlling.ERROR: gettext("Bexio unavailable"),
        },
        "incomplete": gettext("incomplete source"),
        "no_rate": gettext("no rate"),
    }


def register_routes(app):
    app.add_url_rule("/controlling", endpoint="controlling", view_func=controlling_page)
    app.add_url_rule(
        "/api/controlling/month", endpoint="api_controlling_month", view_func=api_controlling_month
    )
    app.add_url_rule(
        "/api/controlling/trend", endpoint="api_controlling_trend", view_func=api_controlling_trend
    )
    app.add_url_rule(
        "/api/controlling/rates", endpoint="api_controlling_rates", view_func=api_controlling_rates
    )
    app.add_url_rule(
        "/api/controlling/rates",
        endpoint="api_controlling_rate_add",
        view_func=api_controlling_rate_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/controlling/rates/<int:rate_id>",
        endpoint="api_controlling_rate_delete",
        view_func=api_controlling_rate_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/controlling/costs",
        endpoint="api_controlling_cost_add",
        view_func=api_controlling_cost_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/controlling/costs/<int:cost_id>",
        endpoint="api_controlling_cost_delete",
        view_func=api_controlling_cost_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/controlling/export.xlsx",
        endpoint="api_controlling_export",
        view_func=api_controlling_export,
    )
