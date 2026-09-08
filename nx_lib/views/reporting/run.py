"""Reporting: sources listing, the curated-report run pipeline, and the
live-SQL sandbox routes (beautify-phase-2a, Task 3).

``/api/reporting/sources``, ``/api/reporting/run``, ``/api/reporting/sql/run``,
``/api/reporting/sql/ack``. ``_forecast_for`` is also used by ``export.py``
(shared by /api/reporting/run and /api/reporting/export so both surfaces
produce the same forecast, #178). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

from typing import Any

import pyodbc
from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...i18n import get_locale
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.contribution import (
    contribution_rows,
    fill_shares,
    is_degenerate,
    is_ratio_metric,
    pick_dimensions,
    single_dimension_definition,
)
from ...reporting.derived import compute_derived
from ...reporting.forecast import compute_forecast
from ...reporting.query import QueryBuildError
from ...reporting.sandbox import MAX_SQL_LEN, SqlSandboxError, humanize_sql_error
from ...reporting.schedule import total_definition
from ...reporting.schema import ReportDefinitionError
from ...reporting.semantic import MetricResolveError
from ...reporting.sources import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, SQL_ROW_CAP, accessible
from ...reporting.sqlformat import format_sql, inline_sql_params
from ...reporting.table_query import TableQueryError, table_source_catalog
from ...reporting.tokens import (
    resolve_token,
    shifted_definition_for_comparison,
    widened_definition_for_forecast,
)
from ...security import has_permission, require_permission
from ._shared import (
    _SQL_TARGET_DB,
    _SQL_TARGET_ENGINES,
    _SQL_TARGET_PERMISSION,
    _allowed_processes,
    _authorize_sql_target,
    _catalog_for_source,
    _effective_sources,
    _execute,
    _get_effective_source,
    _has_acked,
    _json_safe,
    _layout_block,
    _metrics_for_source,
    _prepare_run,
    _run_sql,
)


def _accessible_sql_targets():
    """RO SQL targets the caller may use -> RO connection factories (gated like the
    SQL sandbox). serialize_target() owns and closes each connection it yields."""
    out = {}
    for target, engine in _SQL_TARGET_ENGINES.items():
        perm = _SQL_TARGET_PERMISSION.get(target)
        if perm and not has_permission(perm):
            continue
        if engine is None:
            continue
        out[target] = lambda e=engine: e.raw_connection()
    return out


def _resolved_dates_meta(rd):
    """[{field, token, n?, start, end}] for each token filter (inclusive display
    range) — the run response's transparency metadata."""
    out = []
    for f in rd.get("filters") or []:
        value = f.get("value")
        if not isinstance(value, dict):
            continue
        try:
            start, end = resolve_token(value)
        except ValueError as e:
            current_app.logger.warning(
                f"reporting: _resolved_dates_meta could not resolve token {value!r}: {e}"
            )
            continue
        item = {
            "field": f.get("field"),
            "token": value.get("token"),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if value.get("n") is not None:
            item["n"] = value["n"]
        out.append(item)
    return out


def _forecast_for(rd, columns, rows):
    """Forecast block for one run result — shared by /api/reporting/run and
    /api/reporting/export so both surfaces produce the same forecast (#178).

    Refits on a widened lookback window when the definition qualifies (real
    history beats the visible window for fit quality), falling back to the
    visible rows on any failure. The auto horizon still resolves from the
    VISIBLE `rows` (via compute_forecast's `visible_rows` param) so widening
    the lookback changes fit quality only, never how many buckets project.
    """
    fit_columns, fit_rows = columns, rows
    widened = widened_definition_for_forecast(rd)
    if widened is not None:
        try:
            w_columns, w_sql, w_params, w_engine = _prepare_run(widened)
            fit_columns, fit_rows = w_columns, _execute(w_engine, w_sql, w_params)
        except Exception as e:
            current_app.logger.warning(f"reporting forecast lookback skipped: {e}")
    return compute_forecast(
        rd, fit_columns, fit_rows, visible_rows=rows, carry_forward=_level_metric_indexes(rd)
    )


def _level_metric_indexes(rd):
    """Indexes (within rd['metrics']) of latest-mode metrics — levels such as
    the backlog, whose missing buckets the forecast carries forward rather
    than zero-fills. Empty for anything that can't be resolved."""
    try:
        source = _get_effective_source(rd.get("source"))
        modes = _metrics_for_source(source["id"]) if source else {}
        return {
            i
            for i, m in enumerate(rd.get("metrics") or [])
            if (modes.get(m.get("metric")) or {}).get("total_mode") == "latest"
        }
    except Exception:
        return set()


def _rows_json_safe(rows):
    """Apply _json_safe to every cell of every row (JSON response boundary)."""
    return [[_json_safe(v) for v in row] for row in rows]


@require_permission("reporting.view")
def api_sources():
    perms = set(session.get("permissions", []))
    sources = accessible(_effective_sources(), perms)
    procs = _allowed_processes()
    out = []
    for s in sources:
        entry = {"id": s["id"], "label": s["label"], "kind": s["kind"]}
        # The rail groups cards by database; when the health probe is down it
        # falls back to this engine key rather than one card per source label.
        if s.get("engine"):
            entry["engine"] = s["engine"]
        if s["kind"] == "curated":
            provider = s.get("provider") or "docprocessing"
            if provider == "docprocessing":
                try:
                    entry["fields"] = fetch_docprocessing_catalog(procs, str(get_locale()))
                except Exception as e:
                    current_app.logger.warning(f"reporting sources: catalog unavailable: {e}")
                    entry["fields"] = []
                entry["processes"] = procs
            else:  # generic 'table' provider — catalog from the registry columns
                entry["fields"] = table_source_catalog(s.get("columns"))
                entry["processes"] = []
        elif s["kind"] == "sql":
            target = s.get("target", "statistics")
            entry["target"] = target
            entry["acknowledged"] = _has_acked(session.get("userid"))
            # The database this target really reads, so the target picker can
            # name it ("RuntimeDatabase") instead of the registry label.
            entry["db"] = _SQL_TARGET_DB.get(target)
            # False while the target's read-only login is unprovisioned — the
            # UI can say so up front instead of only on a 503 from Run.
            entry["configured"] = _SQL_TARGET_ENGINES.get(target) is not None
        out.append(entry)
    return jsonify(out)


@require_permission("reporting.view")
@limiter.limit("120 per minute")
def api_run():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    try:
        columns, sql, params, engine = _prepare_run(rd)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500
    try:
        rows = _execute(engine, sql, params)
    except Exception as e:
        current_app.logger.error(f"/api/reporting/run exec error: {e}")
        return jsonify({"error": _("Could not run report")}), 500
    pretty = format_sql(sql)
    payload = {
        "columns": [
            {"field": c["field"], "header": c.get("header") or c["field"]} for c in columns
        ],
        "rows": _rows_json_safe(rows),
        "rowCount": len(rows),
        "truncated": len(rows) >= min(int(rd.get("rowLimit", DEFAULT_ROW_LIMIT)), MAX_ROW_LIMIT),
        "sql": sql,
        "sqlPretty": pretty,
        "sqlDisplay": inline_sql_params(pretty, params),
        "params": [_json_safe(p) for p in params],
    }
    try:
        layout, layout_fallback = _layout_block(rd, session.get("userid"))
    except Exception as e:  # a layout problem must never take down the run
        current_app.logger.warning(f"/api/reporting/run layout skipped: {e}")
        layout, layout_fallback = None, None
    # A layout with a "delta" measure needs the prior window even when the
    # report itself never asked for a comparison.
    wants_delta = layout is not None and any(
        m.get("op") == "delta" for m in layout.get("measures") or []
    )
    if rd.get("compare") or wants_delta:
        shifted = shifted_definition_for_comparison(rd)
        if shifted is not None:
            shifted_rd, prior_start, prior_end = shifted
            try:
                c_columns, c_sql, c_params, c_engine = _prepare_run(shifted_rd)
                c_rows = _execute(c_engine, c_sql, c_params)
                payload["comparison"] = {
                    "columns": [
                        {"field": c["field"], "header": c.get("header") or c["field"]}
                        for c in c_columns
                    ],
                    "rows": _rows_json_safe(c_rows),
                    "priorStart": prior_start.isoformat(),
                    "priorEnd": prior_end.isoformat(),
                }
            except Exception as e:
                current_app.logger.warning(f"/api/reporting/run comparison skipped: {e}")
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            payload["forecast"] = _forecast_for(rd, columns, rows)
        except Exception as e:  # a forecast must never take down the run
            current_app.logger.warning(f"/api/reporting/run forecast skipped: {e}")
    if layout is not None:
        payload["layout"] = layout
        try:
            c_rows = None
            if payload.get("comparison"):
                c_rows = [list(r) for r in payload["comparison"]["rows"]]
            payload["derived"] = compute_derived(layout, rd, columns, rows, comparison_rows=c_rows)
        except Exception as e:  # a measure must never take down the run
            current_app.logger.warning(f"/api/reporting/run derived skipped: {e}")
    elif layout_fallback:
        payload["layoutFallback"] = layout_fallback
    # rd is the original request body (tokens intact) — _prepare_run resolves
    # its own local copy. _resolved_dates_meta needs the tokens to produce labels.
    resolved_dates = _resolved_dates_meta(rd)
    if resolved_dates:
        payload["resolvedDates"] = resolved_dates
    return jsonify(payload)


def _grand_total(rd):
    """Single cell of the zero-column clone (the KPI band's own Total)."""
    clone = total_definition(rd)
    clone["metrics"] = [rd["metrics"][0]]
    columns, sql, params, engine = _prepare_run(clone)
    rows = _execute(engine, sql, params)
    cell = rows[0][0] if rows and rows[0] else 0
    try:
        return float(cell) if cell is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


@require_permission("reporting.view")
@limiter.limit("120 per minute")
def api_contribution():
    """Decompose the first metric's change vs. the shifted prior window by a
    few categorical dimensions (spec 2026-09-07-reporting-contribution-analysis).
    Every query goes through _prepare_run, so grants/scope equal the report's."""
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    metrics = rd.get("metrics") or []
    if not metrics or not isinstance(metrics[0], dict) or not metrics[0].get("metric"):
        return jsonify({"error": _("This report has no measure to explain.")}), 400
    try:
        shifted = shifted_definition_for_comparison(rd)
    except ValueError as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    if shifted is None:
        return jsonify(
            {
                "error": _(
                    "No comparison window — the report needs exactly one relative-date filter."
                )
            }
        ), 400
    shifted_rd, prior_start, prior_end = shifted
    source = _get_effective_source(rd.get("source"))
    if source is None or source.get("kind") != "curated":
        return jsonify({"error": _("This report definition is invalid or outdated.")}), 400
    if not has_permission(source["permission"]):
        return jsonify({"error": _("Not authorized for this source")}), 403
    metric_code = metrics[0]["metric"]
    try:
        catalog, _fields, _filterable, _sortable = _catalog_for_source(source)
        source_metrics = _metrics_for_source(source["id"], get_locale())
        current_total = _grand_total(rd)
        prior_total = _grand_total(shifted_rd)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/contribution prepare error: {e}")
        return jsonify({"error": _("Could not build report")}), 500

    metric_def = source_metrics.get(metric_code) or {}
    is_ratio = is_ratio_metric(metric_def)
    dimensions: list[dict[str, Any]] = []
    skipped: list[str] = []
    # Every candidate, in order; stop at three that actually explain something.
    for dim in pick_dimensions(catalog, rd.get("filters") or [], cap=None):
        if len(dimensions) >= 3:
            break
        field = dim["field"]
        try:
            c_cols, c_sql, c_params, c_engine = _prepare_run(
                single_dimension_definition(rd, field, metric_code)
            )
            p_cols, p_sql, p_params, p_engine = _prepare_run(
                single_dimension_definition(shifted_rd, field, metric_code)
            )
            c_rows = _execute(c_engine, c_sql, c_params)
            p_rows = _execute(p_engine, p_sql, p_params)
            rows = contribution_rows(c_rows, p_rows, top=8)
        except PermissionError:
            return jsonify({"error": _("Not authorized for this source")}), 403
        except Exception as e:  # one unqueryable column must not sink the drawer
            current_app.logger.warning(f"/api/reporting/contribution skipped {field}: {e}")
            skipped.append(field)
            continue
        if is_degenerate(c_rows, p_rows, rows):
            # e.g. WorkItemID / an import file name: one row per value, so the
            # top 8 are arbitrary and "(other)" carries the whole change.
            skipped.append(field)
            continue
        dimensions.append(
            {
                "field": field,
                "label": dim.get("label") or field,
                "rows": rows,
            }
        )
    fill_shares(dimensions, current_total - prior_total, is_ratio)
    return jsonify(
        {
            "priorStart": prior_start.isoformat(),
            "priorEnd": prior_end.isoformat(),
            "metric": metric_code,
            "metricLabel": metric_def.get("label") or metric_code,
            "isRatio": is_ratio,
            "currentTotal": current_total,
            "priorTotal": prior_total,
            "dimensions": dimensions,
            "skipped": skipped,
        }
    )


def _sandbox_error_message(e):
    """Translated user-facing message for a SqlSandboxError, keyed by rule.

    The raw English message stays in the response's `detail` field; dynamic
    bits (keyword / construct name) arrive via e.token. Unknown rules fall
    back to the raw message rather than hiding information.
    """
    token = getattr(e, "token", None) or ""
    messages = {
        "empty": _("SQL is required."),
        "too_long": _("The SQL exceeds {n} characters.").format(n=MAX_SQL_LEN),
        "blocked_keyword": _("Disallowed keyword: {kw}").format(kw=token),
        "parse": _("The SQL could not be parsed."),
        "multi_statement": _("Exactly one statement is allowed."),
        "not_select": _("Only SELECT / WITH / set operations are allowed."),
        "forbidden_node": _("Disallowed construct: {kw}").format(kw=token),
        "tsql_limit": _("T-SQL does not support LIMIT — use TOP (n) instead."),
    }
    return messages.get(e.rule, str(e))


@require_permission("reporting.sql.run")
@limiter.limit("20 per minute")
def api_sql_run():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    userid = session.get("userid")
    username = session.get("username")
    if not userid:
        return jsonify({"error": _("Not authenticated")}), 401
    if not _has_acked(userid):
        return jsonify({"error": _("Acknowledgment required"), "needAck": True}), 409
    try:
        _authorize_sql_target(rd.get("target"))
        columns, rows = _run_sql(rd.get("target"), rd.get("sql"), userid=userid, username=username)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this SQL target")}), 403
    except SqlSandboxError as e:
        return jsonify({"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}), 400
    except ReportDefinitionError as e:
        return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
    except RuntimeError:
        return jsonify({"error": _("SQL source is not configured")}), 503
    except pyodbc.ProgrammingError as e:
        # The sandbox already proved the statement is a single read-only
        # SELECT, so anything the driver still rejects at this point (unknown
        # table/column, ambiguous alias, a clause SQL Server won't take there)
        # is bad user input, not a server fault -- 400, and logged as a
        # warning so a typo in the editor stops paging the app-error
        # dashboards. Connection/timeout failures stay 500 below.
        detail = humanize_sql_error(str(e))
        current_app.logger.warning(f"/api/reporting/sql/run rejected: {detail}")
        return jsonify({"error": _("Could not run query"), "detail": detail}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/sql/run exec error: {e}")
        return jsonify(
            {"error": _("Could not run query"), "detail": humanize_sql_error(str(e))}
        ), 500
    return jsonify(
        {
            "columns": columns,
            "rows": _rows_json_safe(rows),
            "rowCount": len(rows),
            "truncated": len(rows) >= SQL_ROW_CAP,
        }
    )


@require_permission("reporting.sql.run")
@limiter.limit("10 per minute")
def api_sql_ack():
    userid = session.get("userid")
    if not userid:
        return jsonify({"error": _("Not authenticated")}), 401
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "IF NOT EXISTS (SELECT 1 FROM ReportingSqlAck WHERE UserID = ?) "
            "INSERT INTO ReportingSqlAck (UserID) VALUES (?)",
            (userid, userid),
        )
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/sql/ack error: {e}")
        return jsonify({"error": _("Could not record acknowledgment")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule("/api/reporting/sources", endpoint="reporting_sources", view_func=api_sources)
    app.add_url_rule(
        "/api/reporting/run",
        endpoint="reporting_run",
        view_func=api_run,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/sql/run",
        endpoint="reporting_sql_run",
        view_func=api_sql_run,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/sql/ack",
        endpoint="reporting_sql_ack",
        view_func=api_sql_ack,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/contribution",
        endpoint="reporting_contribution",
        view_func=api_contribution,
        methods=["POST"],
    )
