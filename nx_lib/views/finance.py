"""Sydoc Finance (#408): the page, one JSON endpoint per section, a CSV export.

The page is a shell that knows the month and the section list; every section
loads itself from /api/finance/section/<key> so a source that is down (the
Neuzugaenge view is broken on INT, #329) shows its error in place while the
other nine render. The figures come from the registered reporting sources
through the same loaders and the same query builder Reporting uses --
nx_lib/finance.py has the spec, this module only runs it.

finance.view is the whole gate: the 'table' provider applies no row scoping,
so the code is for Sydoc's own accounting and is never granted to a customer
profile (0138).
"""

import datetime as dt

from flask import Response, abort, current_app, jsonify, render_template, request
from flask_babel import format_date, get_locale, gettext

from ..extensions import limiter
from ..finance import (
    SECTIONS,
    SECTIONS_BY_KEY,
    FinanceSpecError,
    assemble_section,
    build_section_queries,
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
from ..security import page_visibility, require_permission
from .reporting._shared import (
    _CURATED_ENGINES,
    _execute,
    _get_effective_source,
    _metrics_for_source,
)


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
        )
    label = source.get("label")
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        return error_section(
            section, gettext("The source's database is not configured."), source_label=label
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
        )
    return assemble_section(
        section,
        queries,
        rows,
        source_label=label,
        metric_label=lambda code: (metrics.get(code) or {}).get("label") or code,
        translate=gettext,
    )


@require_permission("finance.view")
def finance():
    today = dt.date.today()
    year, month = parse_month(request.args.get("month"), today)
    is_current = (year, month) == (today.year, today.month)
    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    descriptors = section_descriptors()
    return render_template(
        "finance.html",
        page_visibility=page_visibility(),
        month=month_key(year, month),
        month_label=_month_label(year, month),
        prev_month=month_key(prev_y, prev_m),
        next_month=None if is_current else month_key(next_y, next_m),
        is_current_month=is_current,
        months=[{"value": key, "label": _month_label(y, m)} for key, y, m in month_options(today)],
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
    payload = _section_payload(section, year, month)
    payload["month"] = month_key(year, month)
    return jsonify(payload)


@require_permission("finance.view")
@limiter.limit("20 per minute")
def api_finance_export():
    year, month = parse_month(request.args.get("month"))
    key = month_key(year, month)
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
    ]
    rows = []
    for section in SECTIONS:
        rows.extend(export_rows(_section_payload(section, year, month)))
    return Response(
        rows_to_csv(columns, rows),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="sydoc-finance-{key}.csv"',
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
        "/api/finance/export.csv",
        endpoint="api_finance_export",
        view_func=api_finance_export,
    )
