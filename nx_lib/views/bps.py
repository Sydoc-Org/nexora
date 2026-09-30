"""Sydoc BPS (#415): every hour booked in the BPS timetool, drilled down.

The page is a shell with the period in the URL; one summary request returns
hours and bookings per task / customer / package / person for the period
(the browser builds the drill-down tree from it, in whichever order the
reader picks), plus the same rows for the period before it (the drill-down's
gain/loss column), and each leaf loads its single bookings -- with their
comments -- on demand. The data is the registered ``bps_projects`` reporting
source (0124), read through the same loader and query builder as Reporting
and the Finance page; nx_lib/bps.py has the rules, this module only runs them.

bps.view is the whole gate (0140): the 'table' provider applies no row
scoping and the page names every employee, so the code is internal only.
"""

import datetime as dt

from flask import Response, current_app, jsonify, render_template, request, url_for
from flask_babel import gettext

from .. import bps
from ..extensions import limiter
from ..reporting.export import rows_to_csv
from ..reporting.table_query import TableQueryError, table_source_catalog
from ..security import has_permission, page_visibility, require_permission
from .reporting._shared import _CURATED_ENGINES, _execute, _get_effective_source


def _source():
    """(base_object, catalog, engine, label) of bps_projects, or raise LookupError(message)."""
    source = _get_effective_source(bps.SOURCE)
    if source is None or source.get("provider") != "table" or not source.get("baseObject"):
        raise LookupError(
            gettext("The reporting source %(code)s is not registered.", code=bps.SOURCE)
        )
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        raise LookupError(gettext("The source's database is not configured."))
    return (
        source["baseObject"],
        table_source_catalog(source.get("columns")),
        engine,
        source.get("label"),
    )


def _range():
    return bps.parse_range(request.args.get("from"), request.args.get("to"))


def _error(message, status=200, detail=None):
    # A source that is down is answered in place (200 + error), like the
    # Finance sections; only a malformed request is a 4xx.
    return jsonify({"error": message, "detail": detail}), status


def _db_detail(exc):
    text = str(exc).strip().splitlines()
    return text[0][:200] if text else None


@require_permission("bps.view")
def bps_page():
    first, last = _range()
    today = dt.date.today()
    prev_first, prev_last = bps.previous_range(first, last)
    nxt = bps.next_range(first, last, today)
    return render_template(
        "bps.html",
        page_visibility=page_visibility(),
        range_from=first.isoformat(),
        range_to=last.isoformat(),
        today=today.isoformat(),
        prev_href=url_for("bps", **{"from": prev_first.isoformat(), "to": prev_last.isoformat()}),
        next_href=(
            url_for("bps", **{"from": nxt[0].isoformat(), "to": nxt[1].isoformat()})
            if nxt
            else None
        ),
        can_finance=has_permission("finance.view"),
        billable_tasks=list(bps.BILLABLE_TASKS),
        preparation=list(bps.PREPARATION),
    )


@require_permission("bps.view")
@limiter.limit("120 per minute")
def api_bps_summary():
    first, last = _range()
    try:
        base_object, catalog, engine, label = _source()
        combos_q, days_q = bps.summary_queries(base_object, catalog, first, last)
        prev_first, prev_last = bps.previous_range(first, last)
        prev_q, _ = bps.summary_queries(base_object, catalog, prev_first, prev_last)
    except LookupError as e:
        return _error(str(e))
    except (bps.BpsSpecError, TableQueryError) as e:
        current_app.logger.warning(f"bps: source is misconfigured: {e}")
        return _error(gettext("This page does not match its registered source."), detail=str(e))
    try:
        combos = _execute(engine, *combos_q)
        days = _execute(engine, *days_q)
        prev_combos = _execute(engine, *prev_q)
    except Exception as e:
        current_app.logger.warning(f"bps: summary query failed: {e}")
        return _error(gettext("Could not read the source."), detail=_db_detail(e))
    payload = bps.summary_payload(combos, days, first, last)
    prev = bps.summary_payload(prev_combos, [], prev_first, prev_last)
    payload["prev"] = {"from": prev["from"], "to": prev["to"], "rows": prev["rows"]}
    payload["source"] = label
    payload["error"] = None
    return jsonify(payload)


@require_permission("bps.view")
@limiter.limit("240 per minute")
def api_bps_entries():
    first, last = _range()
    where = {
        "Aufgabe": request.args.get("task"),
        "Kunde": request.args.get("customer"),
        "Projektpaket": request.args.get("package"),
        "Benutzer": request.args.get("person"),
    }
    # The page only knows cleaned names ("Astrid  Schicker" -> "Astrid Schicker"),
    # which an SQL '=' on the raw column would miss: the person is matched
    # below, in Python, on the cleaned value.
    sql_where = {k: v for k, v in where.items() if k != "Benutzer"}
    try:
        base_object, catalog, engine, _label = _source()
        sql, params = bps.entries_query(base_object, catalog, first, last, sql_where)
    except LookupError as e:
        return _error(str(e))
    except (bps.BpsSpecError, TableQueryError) as e:
        return _error(gettext("This page does not match its registered source."), detail=str(e))
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.warning(f"bps: entries query failed: {e}")
        return _error(gettext("Could not read the source."), detail=_db_detail(e))
    entries = bps.entries_payload(rows)
    person = where["Benutzer"]
    if person:
        entries = [e for e in entries if e["person"] == bps.clean_name(person)]
    return jsonify(
        {"entries": entries, "truncated": len(rows) >= bps.ENTRIES_ROW_CAP, "error": None}
    )


@require_permission("bps.view")
@limiter.limit("60 per minute")
def api_bps_months():
    try:
        base_object, catalog, engine, _label = _source()
        sql, params = bps.months_query(base_object, catalog)
    except LookupError as e:
        return _error(str(e))
    except (bps.BpsSpecError, TableQueryError) as e:
        return _error(gettext("This page does not match its registered source."), detail=str(e))
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.warning(f"bps: months query failed: {e}")
        return _error(gettext("Could not read the source."), detail=_db_detail(e))
    return jsonify({"months": bps.months_payload(rows), "error": None})


@require_permission("bps.view")
@limiter.limit("20 per minute")
def api_bps_export():
    first, last = _range()
    try:
        base_object, catalog, engine, _label = _source()
        sql, params = bps.entries_query(base_object, catalog, first, last, {})
        # The export is the whole period: lift the page's row cap.
        sql = sql.replace(f"TOP ({bps.ENTRIES_ROW_CAP})", "TOP (200000)", 1)
        rows = _execute(engine, sql, params)
    except LookupError as e:
        return Response(str(e), status=503, mimetype="text/plain")
    except Exception as e:
        current_app.logger.warning(f"bps: export failed: {e}")
        return Response(gettext("Could not read the source."), status=503, mimetype="text/plain")
    columns = [
        {"field": "date", "header": gettext("Date")},
        {"field": "customer", "header": gettext("Customer")},
        {"field": "package", "header": gettext("Package")},
        {"field": "task", "header": gettext("Task")},
        {"field": "person", "header": gettext("Person")},
        {"field": "hours", "header": gettext("Hours")},
        {"field": "billable", "header": gettext("Billable")},
        {"field": "comment", "header": gettext("Comment")},
    ]
    labels = {"billable": gettext("yes"), "service": gettext("no"), "absence": gettext("absence")}
    out = [
        [
            e["date"],
            e["customer"],
            e["package"],
            e["task"],
            e["person"],
            e["hours"],
            labels[e["category"]],
            e["comment"],
        ]
        for e in bps.entries_payload(rows)
    ]
    name = f"sydoc-bps-{first.isoformat()}_{last.isoformat()}.csv"
    return Response(
        rows_to_csv(columns, out),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            # Named employees' hours: never cache.
            "Cache-Control": "no-store",
        },
    )


def register_routes(app):
    app.add_url_rule("/bps", endpoint="bps", view_func=bps_page)
    app.add_url_rule("/api/bps/summary", endpoint="api_bps_summary", view_func=api_bps_summary)
    app.add_url_rule("/api/bps/entries", endpoint="api_bps_entries", view_func=api_bps_entries)
    app.add_url_rule("/api/bps/months", endpoint="api_bps_months", view_func=api_bps_months)
    app.add_url_rule("/api/bps/export.csv", endpoint="api_bps_export", view_func=api_bps_export)
