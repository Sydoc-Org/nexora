"""Reporting: export routes (beautify-phase-2a, Task 3).

``/api/reporting/export`` (a curated run or a live-SQL sandbox result ->
.xlsx/.csv download) and ``/api/reporting/export/grid`` (a client-supplied
result grid, e.g. a pivot matrix -> download). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

import base64
import re

from flask import Response, current_app, jsonify, request, session
from flask_babel import gettext as _

from ...extensions import limiter
from ...reporting.derived import compute_derived
from ...reporting.export import derived_export_rows, rows_to_csv, rows_to_xlsx
from ...reporting.forecast import forecast_export_rows
from ...reporting.query import QueryBuildError
from ...reporting.sandbox import SqlSandboxError
from ...reporting.schema import ReportDefinitionError, validate_sql_definition
from ...reporting.semantic import MetricResolveError
from ...reporting.sources import MAX_ROW_LIMIT
from ...reporting.table_query import TableQueryError
from ...security import has_permission, require_permission
from ._shared import (
    _SQL_TARGETS,
    _authorize_sql_target,
    _execute,
    _has_acked,
    _layout_block,
    _prepare_run,
    _run_sql,
)
from .run import _forecast_for, _sandbox_error_message

_EXPORT_FORMATS = {"xlsx", "csv"}


def _safe_report_name(title):
    """Filesystem/header-safe base filename for an export download."""
    return re.sub(r'[\x00-\x1f\x7f";]', "_", (title or "report").strip()) or "report"


def _resolve_export_format(value):
    """Normalize a requested export format to a supported one (defaults to xlsx)."""
    fmt = (value or "xlsx").lower()
    return fmt if fmt in _EXPORT_FORMATS else "xlsx"


_CHART_IMAGE_PREFIX = "data:image/png;base64,"
_CHART_IMAGE_MAX = 2_000_000  # decoded bytes


def _parse_chart_image(value):
    """Decode a client-supplied chart data-URL; returns PNG bytes or None on anything dubious."""
    if not isinstance(value, str) or not value.startswith(_CHART_IMAGE_PREFIX):
        return None
    try:
        raw = base64.b64decode(value[len(_CHART_IMAGE_PREFIX) :], validate=True)
    except Exception:
        return None
    if len(raw) > _CHART_IMAGE_MAX or raw[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return raw


def _serialize_export(
    columns, rows, title, fmt, chart_png=None, forecast_start=None, extra_rows=None
):
    """Build a Flask download Response for `rows` in the requested format."""
    name = _safe_report_name(title)
    if fmt == "csv":
        return Response(
            rows_to_csv(columns, rows, extra_rows=extra_rows),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    return Response(
        rows_to_xlsx(
            columns,
            rows,
            title=title or "Report",
            chart_png=chart_png,
            forecast_start=forecast_start,
            extra_rows=extra_rows,
        ),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export():
    rd = request.get_json(silent=True)
    if not isinstance(rd, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    chart_png = _parse_chart_image(rd.pop("chartImage", None))
    fmt = _resolve_export_format(rd.get("format"))
    if rd.get("kind") == "sql":
        if not has_permission("reporting.sql.run"):
            return jsonify({"error": _("Not authorized for live SQL")}), 403
        userid = session.get("userid")
        if not _has_acked(userid):
            return jsonify({"error": _("Acknowledgment required"), "needAck": True}), 409
        try:
            validate_sql_definition(rd, allowed_targets=_SQL_TARGETS)
            _authorize_sql_target(rd["target"])
            columns, rows = _run_sql(
                rd["target"], rd["sql"], userid=userid, username=session.get("username")
            )
        except PermissionError:
            return jsonify({"error": _("Not authorized for this SQL target")}), 403
        except SqlSandboxError as e:
            return jsonify(
                {"error": _sandbox_error_message(e), "rule": e.rule, "detail": str(e)}
            ), 400
        except ReportDefinitionError as e:
            return jsonify({"error": _("Invalid SQL request."), "detail": str(e)}), 400
        except RuntimeError:
            return jsonify({"error": _("SQL source is not configured")}), 503
        except Exception as e:
            current_app.logger.error(f"/api/reporting/export sql error: {e}")
            return jsonify({"error": _("Could not export query")}), 500
        return _serialize_export(
            columns, rows, rd.get("title") or _("Report"), fmt, chart_png=chart_png
        )
    try:
        columns, sql, params, engine = _prepare_run(rd)
        rows = _execute(engine, sql, params)
    except PermissionError:
        return jsonify({"error": _("Not authorized for this source")}), 403
    except (ReportDefinitionError, QueryBuildError, TableQueryError, MetricResolveError) as e:
        return jsonify(
            {"error": _("This report definition is invalid or outdated."), "detail": str(e)}
        ), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/export error: {e}")
        return jsonify({"error": _("Could not export report")}), 500
    forecast_start = None
    fc_req = rd.get("forecast")
    if isinstance(fc_req, dict) and fc_req.get("enabled"):
        try:
            fc = _forecast_for(rd, columns, rows)
            if fc and not fc.get("unavailable"):
                columns, rows, forecast_start = forecast_export_rows(
                    columns, rows, fc, marker_header=_("Forecast")
                )
        except Exception as e:
            current_app.logger.warning(f"/api/reporting/export forecast skipped: {e}")
    extra_rows = None
    layout, _fallback = _layout_block(rd, session.get("userid"))
    if layout is not None:
        try:
            derived = compute_derived(layout, rd, columns, rows)
            extra_rows = derived_export_rows(layout, derived, header_label=_("Measures"))
        except Exception as e:
            current_app.logger.warning(f"/api/reporting/export derived skipped: {e}")
    return _serialize_export(
        columns,
        rows,
        rd.get("title") or _("Report"),
        fmt,
        chart_png=chart_png,
        forecast_start=forecast_start,
        extra_rows=extra_rows,
    )


@require_permission("reporting.export")
@limiter.limit("30 per minute")
def api_export_grid():
    """Serialize a client-supplied result grid (e.g. a pivot matrix) to a file.

    The chart/pivot result views aggregate client-side, so the caller sends the
    already-computed {columns, rows} it is displaying. No DB access happens here;
    the same reporting.export permission and formula-injection guard still apply.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    chart_png = _parse_chart_image(payload.pop("chartImage", None))
    raw_cols = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(raw_cols, list) or not raw_cols or not isinstance(rows, list):
        return jsonify({"error": _("columns and rows are required")}), 400
    columns = []
    for c in raw_cols:
        if isinstance(c, dict):
            header = c.get("header") or c.get("field") or ""
            columns.append({"field": c.get("field") or header, "header": header})
        else:
            columns.append({"field": str(c), "header": str(c)})
    rows = [list(r) if isinstance(r, list | tuple) else [r] for r in rows[:MAX_ROW_LIMIT]]
    fmt = _resolve_export_format(payload.get("format"))
    return _serialize_export(
        columns, rows, payload.get("title") or _("Report"), fmt, chart_png=chart_png
    )


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/export",
        endpoint="reporting_export",
        view_func=api_export,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/export/grid",
        endpoint="reporting_export_grid",
        view_func=api_export_grid,
        methods=["POST"],
    )
