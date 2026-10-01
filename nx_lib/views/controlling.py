"""Sydoc Controlling (#433): margin per client stream -- BPS hours x rate against Bexio.

The page renders its band from Jinja; /api/controlling/month returns the
whole month (summary, per-stream detail with invoice lines, hours by task,
volumes) and /api/controlling/trend the series since January 2025. The rules
live in nx_lib/controlling.py; this module fetches the inputs and runs them:

* BPS hours through the registered ``bps_projects`` source (the BPS page's
  loader and query builder) -- when BPS is down the hours are unknown, and
  the rest of the page still renders;
* the rates of dbo.FinanceRates, the stream <-> Bexio project map of
  dbo.ControllingStreamProjects with the per-invoice overrides of
  dbo.ControllingInvoiceStreams, and the external costs (dbo.ControllingCosts
  plus Bexio purchase bills through dbo.ControllingVendorStreams);
* the Bexio invoices, live (nx_lib/bexio.py, cached for five minutes);
* the documents per stream through the Finance sections' registered sources,
  or from the Finance month-close snapshot.

A month Sydoc Finance has closed is closed here too: Finance's close calls
``close_month`` below, which freezes the Controlling figures in
dbo.ControllingMonthClose (0147); reopening deletes them. A closed month is
served from that snapshot, with the live Bexio invoices next to it.

controlling.view is the whole gate (0145); rates and external costs are
edited with controlling.rates.edit (0147).
"""

import datetime as dt
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Response, current_app, jsonify, render_template, request, session
from flask_babel import format_date, format_datetime, get_locale, gettext

from .. import bexio, controlling, controlling_export
from ..controlling import EARLIEST, STREAMS, Inputs, month_key, shift_month
from ..db import engine_nexora_db
from ..extensions import limiter
from ..reporting.semantic import MetricResolveError
from ..reporting.table_query import TableQueryError, table_source_catalog
from ..security import has_permission, page_visibility, require_permission
from .billing import _links, _message
from .bps import _source as _bps_source
from .finance import LOCAL_TZ, _as_datetime, _closed_months_safe
from .reporting._shared import (
    _CURATED_ENGINES,
    _execute,
    _get_effective_source,
    _metrics_for_source,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
POSITION_WORKERS = 6
#: The trend reads ~20 months of every source (~10 s); it is cached this long
#: per process (?fresh=1 bypasses it, a rate, cost or close clears it).
TREND_TTL = 300
_trend_cache: dict = {}
_trend_lock = threading.Lock()
RATES_EDIT = "controlling.rates.edit"


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


def _nexora_write(sql, params=()):
    """Run one write; returns the row count."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        affected = cur.rowcount
        conn.commit()
        return affected
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
    rows = _nexora_rows(
        "SELECT CostId, Month, StreamKey, Label, Amount, ChangedAt, ChangedBy "
        "FROM dbo.ControllingCosts WHERE Month >= ? AND Month <= ?",
        (dt.date(fy, fm, 1).isoformat(), dt.date(ly, lm, 1).isoformat()),
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
    """(Hours, error message or None) -- BPS down is a state of the page, not a 500."""
    try:
        base_object, catalog, engine, _label = _bps_source()
        sql, params = controlling.hours_query(base_object, catalog, min(months), max(months))
    except LookupError as e:
        return controlling.Hours(), str(e)
    except (controlling.ControllingSpecError, TableQueryError, ValueError) as e:
        current_app.logger.warning(f"controlling: BPS source is misconfigured: {e}")
        return controlling.Hours(), gettext("The BPS source does not match this page.")
    try:
        return controlling.fold_hours(_execute(engine, sql, params)), None
    except Exception as e:
        current_app.logger.warning(f"controlling: BPS hours query failed: {e}")
        return controlling.Hours(), gettext("Could not read the BPS hours.")


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


def _finance_snapshots(month_keys):
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
    """(documents, live where it moved, streams that failed).

    A closed month counts what its Finance snapshot counted -- the figures it
    was invoiced on -- and keeps the live count next to it."""
    live, failed = _live_documents(months)
    snaps = _finance_snapshots([month_key(*ym) for ym in months])
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
    return docs, moved, failed


def _frozen(month_keys):
    """{month key: {snapshot, at, by}} of the asked months Controlling has frozen."""
    if not month_keys:
        return {}
    marks = ",".join("?" * len(month_keys))
    try:
        rows = _nexora_rows(
            "SELECT Month, Payload, ClosedAt, ClosedBy FROM dbo.ControllingMonthClose "
            f"WHERE Month IN ({marks})",
            tuple(month_keys),
        )
    except Exception as e:
        current_app.logger.warning(f"controlling: could not read the month snapshots: {e}")
        return {}
    out = {}
    for month, payload, at, by in rows:
        try:
            out[str(month)] = {"snapshot": json.loads(payload), "at": _as_datetime(at), "by": by}
        except ValueError:
            continue
    return out


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
    return [bexio.normalize_invoice(r, codes) for r in raw], None


def _contact_names(invoices):
    ids = {i["contactId"] for i in invoices if i.get("contactId")}
    try:
        return bexio.contact_names(ids)
    except bexio.BexioError as e:
        current_app.logger.warning(f"controlling: Bexio contact names unavailable: {e}")
        return {}


def _inputs(months, fresh=False, frozen=None):
    """Inputs for `months`. Raises SourceError only when the rates or the
    stream map cannot be read (without them there is no page); BPS, Bexio,
    the bills and the documents degrade to a state of the page."""
    hours, hours_error = _hours(months)
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
    docs, moved, failed = _documents(months)
    invoices, error = _invoices(months, fresh)
    by, unassigned, names = {}, {}, {}
    if invoices is not None:
        linked = {link.contact_id for link in _links()}
        by, unassigned = controlling.assign_invoices(invoices, projects, linked, overrides)
        names = _contact_names(invoices)
        for invs in unassigned.values():
            for inv in invs:
                if inv.get("projectId"):
                    inv["projectName"] = bexio.project_name(inv["projectId"])
    if frozen is None:
        frozen = _frozen([month_key(*ym) for ym in months])
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
        hours_error=hours_error,
        frozen={mk: f["snapshot"] for mk, f in frozen.items()},
        contacts=names,
    )
    return inp, frozen, failed


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


def _closed_stamp(frozen_month):
    if not frozen_month:
        return None
    at = frozen_month["at"]
    local = at.replace(tzinfo=dt.UTC).astimezone(LOCAL_TZ) if at else None
    return {
        "at": at.isoformat() if at else None,
        "atLabel": format_date(local.date(), "dd.MM.yyyy") if local else "",
        "atLong": format_datetime(local, "short", rebase=False) if local else "",
        "by": frozen_month["by"],
    }


def _month_state(year, month, closed_keys, today=None):
    today = today or dt.date.today()
    if (year, month) == (today.year, today.month):
        return "running"
    return "closed" if month_key(year, month) in closed_keys else "open"


def _build_month(year, month, fresh=False, with_positions=True):
    months = [ym for ym in (shift_month(year, month, -1), (year, month)) if ym >= EARLIEST]
    inp, frozen, failed = _inputs(months, fresh)
    mk = month_key(year, month)
    positions = {}
    if with_positions and inp.invoices is not None:
        current = [i for (m, _k), invs in inp.invoices.items() if m == mk for i in invs]
        positions = _positions(current)
    payload = controlling.month_payload(year, month, inp, gettext, positions)
    window_from, window_to, window_ym = bexio.invoice_window(year, month)
    payload.update(
        label=_month_label(year, month),
        state=_month_state(year, month, _closed_months_safe()),
        closed=_closed_stamp(frozen.get(mk)),
        documentsFailed=failed,
        costsError=inp.costs_error,
        window={"from": window_from, "to": window_to, "label": _month_label(*window_ym)},
        error=None,
    )
    return payload


# --------------------------------------------------------------------------
# Month close (called by Sydoc Finance's close and reopen)
# --------------------------------------------------------------------------


def close_month(year, month, by):
    """Freeze the Controlling figures of a month Finance has just closed.

    Never fails Finance's close: a source that is down (or an error) is
    logged and the month is simply served live, as before. Returns True when
    a snapshot was stored."""
    mk = month_key(year, month)
    try:
        inp, _frozen_none, _failed = _inputs([(year, month)], fresh=True, frozen={})
        snap = controlling.snapshot(year, month, inp)
        down = controlling.snapshot_problems(snap)
        if down:
            current_app.logger.warning(
                f"controlling: {mk} not frozen, sources down: {', '.join(down)}"
            )
            return False
        _nexora_write("DELETE FROM dbo.ControllingMonthClose WHERE Month = ?", (mk,))
        _nexora_write(
            "INSERT INTO dbo.ControllingMonthClose (Month, Payload, ClosedBy) VALUES (?, ?, ?)",
            (mk, json.dumps(snap, ensure_ascii=False, default=str), by),
        )
    except Exception as e:
        current_app.logger.error(f"controlling: freezing {mk} failed: {e}")
        return False
    clear_trend_cache()
    current_app.logger.info(f"controlling: {mk} frozen with the Finance close by {by}")
    return True


def reopen_month(year, month):
    """Drop the frozen Controlling figures of a month Finance has reopened."""
    mk = month_key(year, month)
    try:
        _nexora_write("DELETE FROM dbo.ControllingMonthClose WHERE Month = ?", (mk,))
    except Exception as e:
        current_app.logger.error(f"controlling: unfreezing {mk} failed: {e}")
    clear_trend_cache()


def clear_trend_cache():
    """Drop the cached trends (a rate, a cost or a close changed)."""
    with _trend_lock:
        _trend_cache.clear()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


def _rate_summary(year, month):
    """The band's Rate stat: the default CHF/h of the month, since when, and
    how many stream overrides apply. None when the rates cannot be read."""
    try:
        rates = _rates()
    except Exception as e:
        current_app.logger.warning(f"controlling: rates unreadable for the band: {e}")
        return None
    value = controlling.rate_for(rates, controlling.HOURLY, None, year, month)
    if value is None:
        return {"value": None, "since": None, "overrides": 0}
    first = dt.date(year, month, 1)
    current = [
        r
        for r in rates
        if r["kind"] == controlling.HOURLY
        and r["stream"] is None
        and r["from"] <= first
        and (r["to"] is None or first <= r["to"])
    ]
    since = max(current, key=lambda r: r["from"])["from"] if current else None
    overrides = sum(
        1
        for s in STREAMS
        if controlling.rate_for(rates, controlling.HOURLY, s.key, year, month) != value
    )
    return {
        "value": float(value),
        "since": format_date(since, "MMM yyyy") if since else None,
        "overrides": overrides,
    }


@require_permission("controlling.view")
def controlling_page():
    today = dt.date.today()
    year, month = controlling.parse_month(request.args.get("month"))
    is_current = (year, month) == (today.year, today.month)
    prev = shift_month(year, month, -1)
    nxt = shift_month(year, month, 1)
    closed_keys = _closed_months_safe()
    months = []
    ym = (today.year, today.month)
    while ym >= EARLIEST:
        months.append(
            {
                "value": month_key(*ym),
                "label": _month_label(*ym),
                "state": _month_state(ym[0], ym[1], closed_keys, today),
            }
        )
        ym = shift_month(*ym, -1)
    mk = month_key(year, month)
    state = _month_state(year, month, closed_keys, today)
    window_ym = bexio.invoice_window(year, month)[2]
    return render_template(
        "controlling.html",
        page_visibility=page_visibility(),
        month=mk,
        month_label=_month_label(year, month),
        month_name=format_date(dt.date(year, month, 1), "LLLL"),
        month_year=str(year),
        prev_month_name=format_date(dt.date(prev[0], prev[1], 1), "LLLL"),
        prev_month_short=format_date(dt.date(prev[0], prev[1], 1), "MMM"),
        prev_month=month_key(*prev) if prev >= EARLIEST else None,
        next_month=None if is_current else month_key(*nxt),
        state=state,
        closed=_closed_stamp(_frozen([mk]).get(mk)) if state == "closed" else None,
        invoice_month=_month_label(*window_ym),
        rate=_rate_summary(year, month),
        today=today.isoformat(),
        months=months,
        streams=[controlling.stream_descriptor(s, gettext) for s in STREAMS],
        can_edit_rates=has_permission(RATES_EDIT),
    )


def _error(e, status=200):
    # A source that is down is answered in place (200 + error), like Finance/BPS.
    return jsonify({"error": str(e), "detail": getattr(e, "detail", None)}), status


@require_permission("controlling.view")
@limiter.limit("60 per minute")
def api_controlling_month():
    year, month = controlling.parse_month(request.args.get("month"))
    try:
        payload = _build_month(year, month, fresh=request.args.get("fresh") == "1")
    except SourceError as e:
        return _error(e)
    return jsonify(payload)


@require_permission("controlling.view")
@limiter.limit("30 per minute")
def api_controlling_trend():
    """Every month from January 2025 to the current one, the requested ?month marked."""
    fresh = request.args.get("fresh") == "1"
    today = dt.date.today()
    key = (month_key(today.year, today.month), str(get_locale()))
    now = time.monotonic()
    with _trend_lock:
        hit = _trend_cache.get(key)
    if hit and hit[0] > now and not fresh:
        return jsonify(hit[1])
    months = controlling.months_between(EARLIEST, (today.year, today.month))
    try:
        inp, frozen, _failed = _inputs(months, fresh=fresh)
    except SourceError as e:
        return _error(e)
    payload = controlling.trend_payload(months, inp, gettext)
    closed_keys = _closed_months_safe()
    payload["states"] = [_month_state(y, m, closed_keys, today) for y, m in months]
    payload["labels"] = [_month_label(y, m) for y, m in months]
    payload["bexioError"] = inp.bexio_error
    payload["hoursError"] = inp.hours_error
    payload["error"] = None
    if not inp.bexio_error and not inp.costs_error and not inp.hours_error:
        with _trend_lock:
            _trend_cache[key] = (now + TREND_TTL, payload)
            while len(_trend_cache) > 16:
                _trend_cache.pop(next(iter(_trend_cache)))
    return jsonify(payload)


@require_permission("controlling.view")
@limiter.limit("60 per minute")
def api_controlling_rates():
    try:
        rates = _rates()
    except Exception as e:
        current_app.logger.warning(f"controlling: rates unreadable: {e}")
        return jsonify({"error": gettext("Could not read the rates.")}), 503
    payload = controlling.rates_payload(rates)
    for r in payload:
        at = _as_datetime(r["changedAt"]) if r["changedAt"] else None
        r["changedLabel"] = format_date(at.date(), "dd.MM.yyyy") if at else ""
    return jsonify(
        {
            "rates": payload,
            "streams": [{"key": s.key, "label": s.label} for s in STREAMS],
            "kinds": list(controlling.RATE_KINDS),
            "canEdit": has_permission(RATES_EDIT),
        }
    )


def _rate_body(ignore_id=None):
    """(clean values, None) or (None, error response) of a submitted rate."""
    body = request.get_json(silent=True) or {}
    try:
        kind, stream, value, start, end = controlling.check_rate(
            body.get("kind") or controlling.HOURLY,
            body.get("stream"),
            body.get("value"),
            body.get("from"),
            body.get("to"),
        )
        clash = controlling.rate_overlap(_rates(), kind, stream, start, end, ignore_id)
    except ValueError as e:
        return None, (jsonify({"error": gettext(str(e))}), 400)
    except Exception as e:
        current_app.logger.warning(f"controlling: rates unreadable: {e}")
        return None, (jsonify({"error": gettext("Could not read the rates.")}), 503)
    if clash:
        message = gettext(
            "Overlaps the rate valid %(start)s to %(end)s. Shorten that one first.",
            start=clash["from"].isoformat()[:7],
            end=clash["to"].isoformat()[:7] if clash["to"] else gettext("open"),
        )
        return None, (jsonify({"error": message}), 409)
    return (kind, stream, value, start, end), None


@require_permission(RATES_EDIT)
@limiter.limit("20 per minute")
def api_controlling_rate_add():
    clean, err = _rate_body()
    if err:
        return err
    kind, stream, value, start, end = clean
    try:
        # ISO strings, not dates: the legacy ODBC driver cannot bind a date (HYC00).
        _nexora_write(
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
    except Exception as e:
        current_app.logger.error(f"controlling: adding a rate failed: {e}")
        return jsonify({"error": gettext("Could not save the rate.")}), 500
    clear_trend_cache()
    current_app.logger.info(
        f"controlling: rate {kind} {stream or 'default'} {value} from {start} added by {_actor()}"
    )
    return jsonify({"ok": True})


@require_permission(RATES_EDIT)
@limiter.limit("20 per minute")
def api_controlling_rate_edit(rate_id):
    clean, err = _rate_body(ignore_id=int(rate_id))
    if err:
        return err
    kind, stream, value, start, end = clean
    try:
        affected = _nexora_write(
            "UPDATE dbo.FinanceRates SET Kind = ?, StreamKey = ?, Value = ?, ValidFrom = ?, "
            "ValidTo = ?, ChangedBy = ?, ChangedAt = SYSUTCDATETIME() WHERE RateId = ?",
            (
                kind,
                stream,
                str(value),
                start.isoformat(),
                end.isoformat() if end else None,
                _actor(),
                int(rate_id),
            ),
        )
    except Exception as e:
        current_app.logger.error(f"controlling: editing rate {rate_id} failed: {e}")
        return jsonify({"error": gettext("Could not save the rate.")}), 500
    if not affected:
        return jsonify({"error": gettext("No such rate.")}), 404
    clear_trend_cache()
    current_app.logger.info(f"controlling: rate {rate_id} edited by {_actor()}")
    return jsonify({"ok": True})


@require_permission(RATES_EDIT)
@limiter.limit("20 per minute")
def api_controlling_rate_delete(rate_id):
    try:
        affected = _nexora_write("DELETE FROM dbo.FinanceRates WHERE RateId = ?", (int(rate_id),))
    except Exception as e:
        current_app.logger.error(f"controlling: deleting rate {rate_id} failed: {e}")
        return jsonify({"error": gettext("Could not delete the rate.")}), 500
    if not affected:
        return jsonify({"error": gettext("No such rate.")}), 404
    clear_trend_cache()
    current_app.logger.info(f"controlling: rate {rate_id} deleted by {_actor()}")
    return jsonify({"ok": True})


@require_permission(RATES_EDIT)
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
        _nexora_write(
            "INSERT INTO dbo.ControllingCosts (Month, StreamKey, Label, Amount, ChangedBy) "
            "VALUES (?, ?, ?, ?, ?)",
            (month.isoformat(), stream, label, str(amount), _actor()),
        )
    except Exception as e:
        current_app.logger.error(f"controlling: adding a cost failed: {e}")
        return jsonify({"error": gettext("Could not save the cost.")}), 500
    clear_trend_cache()
    current_app.logger.info(f"controlling: cost {stream} {month} {amount} added by {_actor()}")
    return jsonify({"ok": True})


@require_permission(RATES_EDIT)
@limiter.limit("20 per minute")
def api_controlling_cost_delete(cost_id):
    try:
        affected = _nexora_write(
            "DELETE FROM dbo.ControllingCosts WHERE CostId = ?", (int(cost_id),)
        )
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
    year, month = controlling.parse_month(request.args.get("month"))
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
        "override": gettext("override rate"),
        "moved": gettext("live data moved"),
        "bps_error": gettext("BPS unavailable"),
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
        endpoint="api_controlling_rate_edit",
        view_func=api_controlling_rate_edit,
        methods=["PUT"],
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
