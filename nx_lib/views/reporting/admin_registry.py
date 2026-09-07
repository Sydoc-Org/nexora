"""Reporting: source- and metric-registry admin routes (beautify-phase-2a,
Task 3).

``/reporting/sources`` + ``/api/reporting/admin/sources[/<id>]``
(``reporting.sources.manage``) and ``/reporting/metrics`` +
``/api/reporting/admin/metrics[/<id>]`` (``reporting.metrics.manage``), plus
the two registry-cache invalidators (also called from
``ops/run_scheduled_reports.py`` after an admin edit). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

import json
import re

from flask import current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import cache, limiter
from ...reporting.semantic import AGGREGATIONS
from ...reporting.sources import code_sources
from ...security import page_visibility, require_permission
from ._shared import _METRICS_CACHE_KEY, _SOURCES_CACHE_KEY, _effective_sources


def invalidate_reporting_sources() -> None:
    """Drop the cached sources registry so the next _load_db_sources() re-queries."""
    cache.delete(_SOURCES_CACHE_KEY)


def invalidate_reporting_metrics() -> None:
    """Drop the cached metrics registry so the next _load_db_metrics() re-queries."""
    cache.delete(_METRICS_CACHE_KEY)


# ---- Source-registry admin (reporting.sources.manage) ----------------------

_SOURCE_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _validate_source_payload(p):
    """Return an error string for an invalid registry payload, else None."""
    if not isinstance(p, dict):
        return _("Invalid body")
    if not _SOURCE_CODE_RE.match((p.get("code") or "").strip()):
        return _("code must be 1-64 chars: letters, digits, . _ -")
    if p.get("kind") not in ("curated", "sql"):
        return _("kind must be 'curated' or 'sql'")
    if not (p.get("label") or "").strip():
        return _("label is required")
    if not (p.get("permission") or "").strip():
        return _("permission is required")
    cols = p.get("columns")
    if isinstance(cols, str) and cols.strip():
        try:
            json.loads(cols)
        except (ValueError, TypeError):
            return _("columns must be valid JSON")
    return None


def _columns_to_json(columns):
    if columns is None or columns == "":
        return None
    if isinstance(columns, str):
        return columns if columns.strip() else None
    return json.dumps(columns, ensure_ascii=False)


def _source_insert_params(p):
    return (
        p["code"].strip(),
        p["kind"],
        p["label"].strip(),
        p["permission"].strip(),
        p.get("engine") or None,
        p.get("target") or None,
        p.get("provider") or None,
        p.get("baseObject") or None,
        _columns_to_json(p.get("columns")),
        1 if p.get("enabled", True) else 0,
        int(p.get("sortOrder") or 100),
    )


# ---- Metrics-registry admin (reporting.metrics.manage) --------------------

_METRIC_CODE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_metric_payload(p):
    """Return an error string for an invalid metric payload, else None."""
    if not isinstance(p, dict):
        return _("Invalid body")
    if not _METRIC_CODE_RE.match((p.get("code") or "").strip()):
        return _("code must start with a letter/underscore: letters, digits, _")
    if not (p.get("sourceId") or "").strip():
        return _("sourceId is required")
    if not (p.get("label") or "").strip():
        return _("label is required")
    agg = (p.get("aggregation") or "").strip()
    if agg not in AGGREGATIONS:
        return _("aggregation must be one of: ") + ", ".join(sorted(AGGREGATIONS))
    if agg != "count" and not (p.get("baseField") or "").strip():
        return _("baseField is required unless aggregation is 'count'")
    return None


def _metric_insert_params(p):
    return (
        p["code"].strip(),
        p["sourceId"].strip(),
        p["label"].strip(),
        (p.get("labelDe") or "").strip() or None,
        (p.get("labelFr") or "").strip() or None,
        (p.get("labelIt") or "").strip() or None,
        p["aggregation"].strip(),
        (p.get("baseField") or "").strip() or None,
        p.get("format") or None,
        1 if p.get("enabled", True) else 0,
        int(p.get("sortOrder") or 100),
    )


@require_permission("reporting.sources.manage")
def reporting_sources_admin():
    return render_template(
        "reporting_sources.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
    )


@require_permission("reporting.sources.manage")
def api_admin_sources_list():
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT SourceID, Code, Kind, Label, Permission, Engine, Target, Provider, "
            "BaseObject, ColumnsJSON, Enabled, SortOrder FROM dbo.ReportingSources "
            "ORDER BY SortOrder, Label"
        )
        rows = [
            {
                "id": r.SourceID,
                "code": r.Code,
                "kind": r.Kind,
                "label": r.Label,
                "permission": r.Permission,
                "engine": r.Engine,
                "target": r.Target,
                "provider": r.Provider,
                "baseObject": r.BaseObject,
                "columnsJson": r.ColumnsJSON,
                "enabled": bool(r.Enabled),
                "sortOrder": r.SortOrder,
            }
            for r in cur.fetchall()
        ]
    except Exception as e:
        current_app.logger.error(f"reporting admin sources list error: {e}")
        return jsonify({"error": _("Could not list sources")}), 500
    finally:
        conn.close()
    return jsonify({"defaults": code_sources(), "rows": rows})


@require_permission("reporting.sources.manage")
@limiter.limit("60 per minute")
def api_admin_sources_create():
    p = request.get_json(silent=True) or {}
    err = _validate_source_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportingSources "
            "(Code, Kind, Label, Permission, Engine, Target, Provider, BaseObject, "
            " ColumnsJSON, Enabled, SortOrder) "
            "OUTPUT INSERTED.SourceID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _source_insert_params(p),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        new_id = inserted[0]
        conn.commit()
        invalidate_reporting_sources()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources create error: {e}")
        return jsonify({"error": _("Could not save source (code already exists?)")}), 500
    finally:
        conn.close()


@require_permission("reporting.sources.manage")
@limiter.limit("60 per minute")
def api_admin_sources_update(source_id):
    p = request.get_json(silent=True) or {}
    err = _validate_source_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        params = (*_source_insert_params(p), source_id)
        cur.execute(
            "UPDATE dbo.ReportingSources SET Code=?, Kind=?, Label=?, Permission=?, "
            "Engine=?, Target=?, Provider=?, BaseObject=?, ColumnsJSON=?, Enabled=?, "
            "SortOrder=?, UpdatedAt=SYSUTCDATETIME() WHERE SourceID=?",
            params,
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_sources()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources update error: {e}")
        return jsonify({"error": _("Could not update source")}), 500
    finally:
        conn.close()


@require_permission("reporting.sources.manage")
def api_admin_sources_delete(source_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportingSources WHERE SourceID = ?", (source_id,))
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_sources()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin sources delete error: {e}")
        return jsonify({"error": _("Could not delete source")}), 500
    finally:
        conn.close()


@require_permission("reporting.metrics.manage")
def reporting_metrics_admin():
    return render_template(
        "reporting_metrics.html",
        logged_in_user=session.get("username", "Unknown"),
        fullname=session.get("fullname"),
        page_visibility=page_visibility(),
    )


@require_permission("reporting.metrics.manage")
def api_admin_metrics_list():
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT MetricID, Code, SourceId, Label, GermanLabel, FrenchLabel, "
            "ItalianLabel, Aggregation, BaseField, Description, Format, Enabled, "
            "SortOrder FROM dbo.ReportingMetrics ORDER BY SortOrder, Label"
        )
        rows = [
            {
                "id": r.MetricID,
                "code": r.Code,
                "sourceId": r.SourceId,
                "label": r.Label,
                "labelDe": r.GermanLabel,
                "labelFr": r.FrenchLabel,
                "labelIt": r.ItalianLabel,
                "aggregation": r.Aggregation,
                "baseField": r.BaseField,
                "description": r.Description,
                "format": r.Format,
                "enabled": bool(r.Enabled),
                "sortOrder": r.SortOrder,
            }
            for r in cur.fetchall()
        ]
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics list error: {e}")
        return jsonify({"error": _("Could not list metrics")}), 500
    finally:
        conn.close()
    sources = [{"id": s["id"], "label": s["label"]} for s in _effective_sources()]
    return jsonify({"rows": rows, "sources": sources})


@require_permission("reporting.metrics.manage")
@limiter.limit("60 per minute")
def api_admin_metrics_create():
    p = request.get_json(silent=True) or {}
    err = _validate_metric_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportingMetrics "
            "(Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, "
            "Aggregation, BaseField, Format, Enabled, SortOrder) "
            "OUTPUT INSERTED.MetricID VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _metric_insert_params(p),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        new_id = inserted[0]
        conn.commit()
        invalidate_reporting_metrics()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics create error: {e}")
        return jsonify({"error": _("Could not save metric (code already exists?)")}), 500
    finally:
        conn.close()


@require_permission("reporting.metrics.manage")
@limiter.limit("60 per minute")
def api_admin_metrics_update(metric_id):
    p = request.get_json(silent=True) or {}
    err = _validate_metric_payload(p)
    if err:
        return jsonify({"error": err}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        params = (*_metric_insert_params(p), metric_id)
        cur.execute(
            "UPDATE dbo.ReportingMetrics SET Code=?, SourceId=?, Label=?, GermanLabel=?, "
            "FrenchLabel=?, ItalianLabel=?, Aggregation=?, BaseField=?, Format=?, "
            "Enabled=?, SortOrder=?, UpdatedAt=SYSUTCDATETIME() WHERE MetricID=?",
            params,
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_metrics()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics update error: {e}")
        return jsonify({"error": _("Could not update metric")}), 500
    finally:
        conn.close()


@require_permission("reporting.metrics.manage")
def api_admin_metrics_delete(metric_id):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ReportingMetrics WHERE MetricID = ?", (metric_id,))
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        invalidate_reporting_metrics()
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting admin metrics delete error: {e}")
        return jsonify({"error": _("Could not delete metric")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/reporting/sources",
        endpoint="reporting_sources_admin",
        view_func=reporting_sources_admin,
    )
    app.add_url_rule(
        "/api/reporting/admin/sources",
        endpoint="reporting_admin_sources_list",
        view_func=api_admin_sources_list,
    )
    app.add_url_rule(
        "/api/reporting/admin/sources",
        endpoint="reporting_admin_sources_create",
        view_func=api_admin_sources_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/admin/sources/<int:source_id>",
        endpoint="reporting_admin_sources_update",
        view_func=api_admin_sources_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/admin/sources/<int:source_id>",
        endpoint="reporting_admin_sources_delete",
        view_func=api_admin_sources_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/reporting/metrics",
        endpoint="reporting_metrics_admin",
        view_func=reporting_metrics_admin,
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics",
        endpoint="reporting_admin_metrics_list",
        view_func=api_admin_metrics_list,
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics",
        endpoint="reporting_admin_metrics_create",
        view_func=api_admin_metrics_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics/<int:metric_id>",
        endpoint="reporting_admin_metrics_update",
        view_func=api_admin_metrics_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/admin/metrics/<int:metric_id>",
        endpoint="reporting_admin_metrics_delete",
        view_func=api_admin_metrics_delete,
        methods=["DELETE"],
    )
