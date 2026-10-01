"""Sydoc Finance (#408): the page, one JSON endpoint per section, a CSV export,
and the month close (#415).

The page is a shell that knows the month and the section list; every section
loads itself from /api/finance/section/<key> so a source that is down (the
Neuzugaenge view is broken on INT, #329) shows its error in place while the
other sections render. The figures come from the registered reporting sources
through the same loaders and the same query builder Reporting uses --
nx_lib/finance.py has the spec, this module only runs it.

finance.view is the whole gate: the 'table' provider applies no row scoping,
so the code is for Sydoc's own accounting and is never granted to a customer
profile (0138).

A closed month (dbo.FinanceMonthClose, 0139) is served from its snapshot:
the payload every section had when accounting closed it. The live figures
are still computed next to it and shown only as a difference, because the
sources are edited after a month is invoiced (EM re-exports overwrite the
export date) and the invoice must stay reproducible. finance.month.edit gates
closing and reopening.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

from flask import Response, abort, current_app, jsonify, render_template, request, session
from flask_babel import format_date, format_datetime, format_decimal, get_locale, gettext, ngettext

from .. import finance_export
from ..db import engine_nexora_db
from ..extensions import limiter
from ..finance import (
    SECTIONS,
    SECTIONS_BY_KEY,
    FinanceSpecError,
    assemble_section,
    build_section_queries,
    diff_payload,
    error_section,
    export_rows,
    month_key,
    month_options,
    parse_month,
    section_descriptors,
    shift_month,
)
from ..reporting.export import rows_to_csv
from ..reporting.semantic import MetricResolveError
from ..reporting.table_query import TableQueryError, table_source_catalog
from ..security import has_permission, page_visibility, require_permission
from .reporting._shared import (
    _CURATED_ENGINES,
    _execute,
    _get_effective_source,
    _metrics_for_source,
)

LOCAL_TZ = ZoneInfo("Europe/Zurich")


def _month_label(year, month):
    """'September 2026' in the reader's locale (standalone month name)."""
    return format_date(dt.date(year, month, 1), "LLLL yyyy")


def _db_error_detail(exc):
    """The driver's own first line, the way the reporting sandbox surfaces it."""
    text = str(exc).strip().splitlines()
    return text[0][:200] if text else None


def _section_payload(section, year, month):
    source = _get_effective_source(section.source)
    if source is None or source.get("provider") != "table" or not source.get("baseObject"):
        return error_section(
            section,
            gettext("The reporting source %(code)s is not registered.", code=section.source),
            translate=gettext,
        )
    label = source.get("label")
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        return error_section(
            section,
            gettext("The source's database is not configured."),
            source_label=label,
            translate=gettext,
        )
    catalog = table_source_catalog(source.get("columns"))
    metrics = _metrics_for_source(source["id"], get_locale())
    try:
        queries = build_section_queries(
            section, source["baseObject"], catalog, metrics, year, month
        )
    except (FinanceSpecError, MetricResolveError, TableQueryError) as e:
        current_app.logger.warning(f"finance: section {section.key} is misconfigured: {e}")
        return error_section(
            section,
            gettext("This section does not match its registered source."),
            detail=str(e),
            source_label=label,
            translate=gettext,
        )
    try:
        rows = [_execute(engine, q.sql, q.params) for q in queries]
    except Exception as e:
        current_app.logger.warning(f"finance: section {section.key} query failed: {e}")
        return error_section(
            section,
            gettext("Could not read the source."),
            detail=_db_error_detail(e),
            source_label=label,
            translate=gettext,
        )
    return assemble_section(
        section,
        queries,
        rows,
        source_label=label,
        metric_label=lambda code: (metrics.get(code) or {}).get("label") or code,
        translate=gettext,
    )


# --------------------------------------------------------------------------
# Month close
# --------------------------------------------------------------------------


def _closed(month):
    """{section key: {payload, at, by}} of a closed month; {} when it is open."""
    if engine_nexora_db is None:
        return {}
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SectionKey, Payload, ClosedAt, ClosedBy FROM dbo.FinanceMonthClose "
            "WHERE Month = ?",
            (month,),
        )
        return {
            r[0]: {"payload": json.loads(r[1]), "at": _as_datetime(r[2]), "by": r[3]}
            for r in cur.fetchall()
        }
    finally:
        conn.close()


def _as_datetime(value):
    """ClosedAt as a datetime: the legacy "SQL Server" ODBC driver returns a
    datetime2 column as its text ('2026-09-30 07:37:49'), newer drivers as a
    datetime."""
    if value is None or isinstance(value, dt.datetime):
        return value
    try:
        return dt.datetime.fromisoformat(str(value).strip()[:19])
    except ValueError:
        return None


def _closed_safe(month):
    """_closed(), but a read failure degrades to 'open' (logged) instead of a 500."""
    try:
        return _closed(month)
    except Exception as e:
        current_app.logger.warning(f"finance: could not read the month close of {month}: {e}")
        return {}


def _closed_months():
    """Every month that has a close snapshot, as 'YYYY-MM' keys."""
    if engine_nexora_db is None:
        return set()
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT Month FROM dbo.FinanceMonthClose")
        return {str(r[0]) for r in cur.fetchall()}
    finally:
        conn.close()


def _closed_months_safe():
    """_closed_months(), but a read failure degrades to 'none closed' (logged)."""
    try:
        return _closed_months()
    except Exception as e:
        current_app.logger.warning(f"finance: could not read the closed months: {e}")
        return set()


def _local(at):
    """ClosedAt is stored in UTC (SYSUTCDATETIME); Sydoc reads Swiss time."""
    return at.replace(tzinfo=dt.UTC).astimezone(LOCAL_TZ)


def _closed_info(closed):
    """The close stamp of a month (every section row of it carries the same one)."""
    if not closed:
        return None
    row = next(iter(closed.values()))
    at = row["at"]
    return {
        "at": at.isoformat() if at else None,
        "atLabel": format_datetime(_local(at), "short", rebase=False) if at else "",
        "by": row["by"],
    }


def _actor():
    return (session.get("fullname") or session.get("username") or "?")[:100]


def _month_to_close():
    """((year, month), None) for a close/reopen request, or (None, error response).

    Unlike the page, a write never falls back to a default month: the month
    must be named exactly and must have ended.
    """
    today = dt.date.today()
    raw = str(request.args.get("month") or "")
    year, month = parse_month(raw, today)
    if month_key(year, month) != raw:
        return None, (jsonify({"error": gettext("Unknown month.")}), 400)
    if (year, month) >= (today.year, today.month):
        return None, (
            jsonify({"error": gettext("A month can only be closed once it has ended.")}),
            400,
        )
    return (year, month), None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@require_permission("finance.view")
def finance():
    today = dt.date.today()
    year, month = parse_month(request.args.get("month"), today)
    is_current = (year, month) == (today.year, today.month)
    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    descriptors = section_descriptors()
    translate = gettext  # an alias, so pybabel does not extract the variable as a msgid
    for d in descriptors:
        d["title"] = translate(d["title"]) if d["title"] else None
        d["nav"] = translate(d["nav"])
    options = month_options(today)
    option_keys = {key for key, _y, _m in options}
    closed_months = _closed_months_safe()

    def state(key, y, m):
        if (y, m) == (today.year, today.month):
            return "running"
        return "closed" if key in closed_months else "open"

    prev_key = month_key(prev_y, prev_m)
    return render_template(
        "finance.html",
        page_visibility=page_visibility(),
        month=month_key(year, month),
        month_label=_month_label(year, month),
        month_name=format_date(dt.date(year, month, 1), "LLLL"),
        month_year=str(year),
        today=today.isoformat(),
        prev_month_name=format_date(dt.date(prev_y, prev_m, 1), "LLLL"),
        # Inert at the oldest pickable month, like next at the current one.
        prev_month=prev_key if prev_key in option_keys else None,
        next_month=None if is_current else month_key(next_y, next_m),
        is_current_month=is_current,
        closed=_closed_info(_closed_safe(month_key(year, month))),
        can_close=has_permission("finance.month.edit") and not is_current,
        months=[
            {"value": key, "label": _month_label(y, m), "state": state(key, y, m)}
            for key, y, m in options
        ],
        internal_sections=[d for d in descriptors if d["group"] == "internal"],
        external_sections=[d for d in descriptors if d["group"] == "external"],
        service_sections=[d for d in descriptors if d["group"] == "services"],
    )


@require_permission("finance.view")
@limiter.limit("240 per minute")
def api_finance_section(key):
    section = SECTIONS_BY_KEY.get(key)
    if section is None:
        abort(404)
    year, month = parse_month(request.args.get("month"))
    mkey = month_key(year, month)
    snapshot = None if request.args.get("live") == "1" else _closed_safe(mkey).get(key)
    live = _section_payload(section, year, month)
    live["month"] = mkey
    if snapshot is None:
        live["closed"] = None
        return jsonify(_with_exports(section, live))
    payload = snapshot["payload"]
    payload["month"] = mkey
    payload["closed"] = _closed_info({key: snapshot})
    # None = the live figures could not be read, [] = nothing moved since the close.
    payload["live_diff"] = None if live.get("error") else diff_payload(payload, live)
    return jsonify(_with_exports(section, payload))


def _with_exports(section, payload):
    """The invoice sheets the BPS export offers for this payload (never stored
    in a snapshot: they are derived from its bookings when served)."""
    if section.bookings is not None and not payload.get("error"):
        payload["exports"] = [
            {"key": s.key, "title": s.title, "count": len(s.rows)}
            for s in finance_export.sheets(payload, section.bookings)
        ]
    return payload


def close_month(year, month, by):
    """Snapshot every section of an ended month into dbo.FinanceMonthClose.

    None when closed, else (message, HTTP status). Shared by the close
    route and scripts/finance-close-months.py, which closes the months that
    were invoiced before the page existed.
    """
    mkey = month_key(year, month)
    if engine_nexora_db is None:
        return gettext("Could not close the month."), 503
    if _closed(mkey):
        return gettext("This month is already closed."), 409
    payloads = [_section_payload(s, year, month) for s in SECTIONS]
    failed = [p for p in payloads if p.get("error")]
    if failed:
        names = ", ".join(" · ".join(filter(None, (p["client"], p["title"]))) for p in failed)
        message = gettext(
            "The month cannot be closed while a section cannot be read: %(names)s", names=names
        )
        return message, 409
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        for p in payloads:
            p["month"] = mkey
            cur.execute(
                "INSERT INTO dbo.FinanceMonthClose (Month, SectionKey, Payload, ClosedBy) "
                "VALUES (?, ?, ?, ?)",
                (mkey, p["key"], json.dumps(p, ensure_ascii=False, default=str), by),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"finance: closing {mkey} failed: {e}")
        return gettext("Could not close the month."), 500
    finally:
        conn.close()
    current_app.logger.info(f"finance: {mkey} closed by {by}")
    return None


@require_permission("finance.month.edit")
@limiter.limit("10 per minute")
def api_finance_close():
    ym, err = _month_to_close()
    if err:
        return err
    year, month = ym
    error = close_month(year, month, _actor())
    if error:
        message, status = error
        return jsonify({"error": message}), status
    mkey = month_key(year, month)
    return jsonify({"ok": True, "month": mkey})


@require_permission("finance.month.edit")
@limiter.limit("10 per minute")
def api_finance_reopen():
    ym, err = _month_to_close()
    if err:
        return err
    mkey = month_key(*ym)
    if engine_nexora_db is None:
        return jsonify({"error": gettext("Could not reopen the month.")}), 503
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.FinanceMonthClose WHERE Month = ?", (mkey,))
        affected = cur.rowcount
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"finance: reopening {mkey} failed: {e}")
        return jsonify({"error": gettext("Could not reopen the month.")}), 500
    finally:
        conn.close()
    if not affected:
        return jsonify({"error": gettext("This month is not closed.")}), 404
    current_app.logger.info(f"finance: {mkey} reopened by {_actor()}")
    return jsonify({"ok": True, "month": mkey})


@require_permission("finance.view")
@limiter.limit("20 per minute")
def api_finance_export():
    year, month = parse_month(request.args.get("month"))
    key = month_key(year, month)
    closed = _closed_safe(key)
    columns = [
        {"field": "client", "header": gettext("Client")},
        {"field": "section", "header": gettext("Section")},
        {"field": "basis", "header": gettext("Month basis")},
        {"field": "kind", "header": gettext("Kind")},
        {"field": "dimension", "header": gettext("Dimension")},
        {"field": "group", "header": gettext("Group")},
        {"field": "measure", "header": gettext("Measure")},
        {"field": "value", "header": key},
        {"field": "previous", "header": gettext("Previous month")},
        {"field": "detail", "header": gettext("Detail")},
    ]
    rows = []
    for section in SECTIONS:
        snap = closed.get(section.key)
        payload = snap["payload"] if snap else _section_payload(section, year, month)
        rows.extend(export_rows(payload))
    suffix = "-closed" if closed else ""
    return Response(
        rows_to_csv(columns, rows),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="sydoc-finance-{key}{suffix}.csv"',
            # Private accounting data: never cache (tests/unit/test_static_v_lint.py).
            "Cache-Control": "no-store",
        },
    )


BPS_EXPORT_FORMATS = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _export_labels(month_label):
    return {
        "title": gettext("Sydoc BPS · billable hours"),
        "overview": gettext("Overview"),
        "invoice": gettext("Invoice"),
        "bookings": gettext("Bookings"),
        "bookings_n": lambda n: ngettext("%(num)d booking", "%(num)d bookings", n),
        "hours": gettext("Hours"),
        "billed": gettext("Billed (¼ h)"),
        "total": gettext("Total"),
        "date": gettext("Date"),
        "package": gettext("Package"),
        "task": gettext("Task"),
        "person": gettext("Person"),
        "comment": gettext("Comment"),
        "empty": gettext("No billable hours in %(month)s", month=month_label),
    }


@require_permission("finance.view")
@limiter.limit("20 per minute")
def api_finance_bps_export():
    """The billable BPS hours of a month as .xlsx or .pdf (#408).

    ?sheet=all (default) is every invoice in one file -- one sheet (or PDF
    section) each, behind an overview; ?sheet=<key> is that invoice alone;
    ?files=separate with sheet=all is a .zip holding one file per invoice.
    A closed month exports its snapshot, like the page shows it.
    """
    section = SECTIONS_BY_KEY["bps"]
    fmt = request.args.get("format", "xlsx")
    if fmt not in BPS_EXPORT_FORMATS:
        return jsonify({"error": gettext("Unknown export format.")}), 400
    year, month = parse_month(request.args.get("month"))
    key = month_key(year, month)
    snap = _closed_safe(key).get(section.key)
    payload = snap["payload"] if snap else _section_payload(section, year, month)
    if payload.get("error"):
        return jsonify({"error": payload["error"]}), 503
    sheets = finance_export.sheets(payload, section.bookings)
    wanted = request.args.get("sheet") or "all"
    if wanted != "all":
        sheets = [s for s in sheets if s.key == wanted]
        if not sheets:
            return jsonify({"error": gettext("Nothing to export for this invoice.")}), 404
    month_label = _month_label(year, month)
    labels = _export_labels(month_label)

    def render(items):
        if fmt == "pdf":
            return finance_export.pdf(
                items,
                labels,
                month_label,
                number=lambda v: format_decimal(v, format="#,##0.00"),
            )
        return finance_export.workbook(items, labels, month_label)

    stem = f"sydoc-bps-{key}" + ("-closed" if snap else "")
    if wanted == "all" and request.args.get("files") == "separate" and sheets:
        body = finance_export.zipped([(f"{stem}-{s.key}.{fmt}", render([s])) for s in sheets])
        name, mimetype = f"{stem}.zip", "application/zip"
    else:
        body = render(sheets)
        suffix = "" if wanted == "all" else f"-{wanted}"
        name, mimetype = f"{stem}{suffix}.{fmt}", BPS_EXPORT_FORMATS[fmt]
    return Response(
        body,
        mimetype=mimetype,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            # Private accounting data: never cache (tests/unit/test_static_v_lint.py).
            "Cache-Control": "no-store",
        },
    )


def register_routes(app):
    app.add_url_rule("/finance", endpoint="finance", view_func=finance)
    app.add_url_rule(
        "/api/finance/section/<key>",
        endpoint="api_finance_section",
        view_func=api_finance_section,
    )
    app.add_url_rule(
        "/api/finance/close",
        endpoint="api_finance_close",
        view_func=api_finance_close,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/finance/reopen",
        endpoint="api_finance_reopen",
        view_func=api_finance_reopen,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/finance/export.csv",
        endpoint="api_finance_export",
        view_func=api_finance_export,
    )
    app.add_url_rule(
        "/api/finance/bps-export",
        endpoint="api_finance_bps_export",
        view_func=api_finance_bps_export,
    )
