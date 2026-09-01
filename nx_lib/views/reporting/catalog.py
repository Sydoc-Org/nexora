"""Reporting: field-values and metrics catalog API routes
(beautify-phase-2a, Task 3).

``/api/reporting/field_values`` (distinct values of one whitelisted table
field, #178) and ``/api/reporting/metrics`` (accessible metrics grouped by
source, for the builder). ``_accessible_curated_sources`` also lives here —
it feeds the AI catalog serializer (``ai.py`` does a lazy
``from . import _accessible_curated_sources`` so it keeps resolving
regardless of which submodule defines it). Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...extensions import limiter
from ...i18n import get_locale
from ...reporting.catalog import fetch_docprocessing_catalog
from ...reporting.sources import accessible
from ...reporting.table_query import TableQueryError, build_distinct_query, table_source_catalog
from ...security import has_permission, require_permission
from ._shared import (
    _CURATED_ENGINES,
    _METRIC_LABEL_ATTRS,
    _allowed_processes,
    _catalog_for_source,
    _effective_sources,
    _execute,
    _get_effective_source,
    _load_db_metrics,
)


def _metric_label(m):
    """Locale-aware metric label with English fallback (mirrors the
    Search_Field_Labels convention: a missing translation falls back to Label).

    Request-context only (reads get_locale()); non-request callers — the AI
    catalogs and the scheduler's _metrics_for_source — keep using m['label'].
    """
    attr = _METRIC_LABEL_ATTRS.get(str(get_locale()))
    return (m.get(attr) if attr else None) or m["label"]


def _accessible_curated_sources():
    """Curated sources the caller can access, shaped for the AI catalog serializer."""
    perms = set(session.get("permissions", []))
    allowed_processes = _allowed_processes()
    # Canonical metrics per source so the model can draft metric definitions
    # (the serializer renders them as a per-source `metrics:` line).
    metrics_by_source = {}
    for m in _load_db_metrics().values():
        metrics_by_source.setdefault(m["source_id"], []).append(
            {
                "code": m["code"],
                "label": m["label"],
                "aggregation": m["aggregation"],
                "base_field": m["base_field"],
                "anchor": m.get("anchor"),
            }
        )
    out = []
    for s in accessible(_effective_sources(), perms):
        if s.get("kind") != "curated":
            continue
        provider = s.get("provider") or "docprocessing"
        if provider == "docprocessing":
            # Fields come from the locale-aware Statconfig catalog, scoped to the
            # caller's allowed processes (mirrors /api/reporting/run + api_sources),
            # so the model grounds on the same fields the validator will check.
            try:
                catalog = fetch_docprocessing_catalog(allowed_processes, str(get_locale()))
            except Exception as e:  # a catalog failure degrades to "no fields", never 500
                current_app.logger.warning(f"reporting.ai catalog: docprocessing unavailable: {e}")
                catalog = []
            processes = allowed_processes
        else:
            catalog = table_source_catalog(s.get("columns"))
            processes = s.get("processes") or []
        out.append(
            {
                "id": s.get("id"),
                "label": s.get("label"),
                "fields": catalog,
                "processes": processes,
                "metrics": metrics_by_source.get(s.get("id"), []),
            }
        )
    return out


def _labeled_field_values(rows, allowed=None):
    """(values, labels) from labelWith pair rows [(value, companion), ...]:
    label is "companion.value" (companion lowercased — the app's
    client.process idiom). `allowed` (a set of such labels, from the caller's
    grants) drops every value whose label isn't granted.
    ponytail: a value shared by several companions falls back to its bare
    name — split into per-companion filters if that ever matters."""
    values, labels = [], {}
    for r in rows:
        v = r[0]
        label = f"{str(r[1]).lower()}.{v}" if r[1] is not None else str(v)
        if v not in labels:
            values.append(v)
            labels[v] = label
        elif labels[v] != label:
            labels[v] = str(v)
    if allowed is not None:
        values = [v for v in values if labels.get(v) in allowed]
        labels = {v: labels[v] for v in values}
    return values, labels


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_field_values():
    """Distinct values of one whitelisted field of a table source (#178) —
    powers the wizard's process-scope step for sources without a process
    registry. Source-permission-gated; table provider only."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": _("Invalid JSON body")}), 400
    source = _get_effective_source((body.get("source") or "").strip())
    if (
        source is None
        or source.get("kind") != "curated"
        or (source.get("provider") or "docprocessing") != "table"
    ):
        return jsonify({"error": _("Unknown or unsupported source")}), 400
    if not has_permission(source["permission"]):
        return jsonify({"error": _("Not authorized for this source")}), 403
    engine = _CURATED_ENGINES.get(source.get("engine"))
    if engine is None:
        return jsonify({"error": _("Source engine is not configured")}), 503
    catalog, _fields, _filterable, _sortable = _catalog_for_source(source)
    try:
        field = (body.get("field") or "").strip()
        sql = build_distinct_query(field, source.get("baseObject"), catalog)
        rows = _execute(engine, sql, [])
    except TableQueryError as e:
        return jsonify({"error": _("This request is invalid."), "detail": str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"/api/reporting/field_values exec error: {e}")
        return jsonify({"error": _("Could not load values")}), 500
    if rows and len(rows[0]) > 1:
        meta = next((c for c in catalog if c.get("field") == field), None)
        # grantScoped: the snapshot table carries every Octo process; offer
        # only the ones the caller is granted (= the list the rest of the app
        # shows). UI curation on top of the source-level permission — the run
        # path stays gated by the source grant alone.
        allowed = set(_allowed_processes()) if meta and meta.get("grantScoped") else None
        values, labels = _labeled_field_values(rows, allowed)
        return jsonify({"values": values, "labels": labels})
    return jsonify({"values": [r[0] for r in rows]})


@require_permission("reporting.view")
def api_metrics():
    """Accessible metrics grouped by source id -> [{code,label,aggregation,...}].

    Only metrics bound to a source whose permission the caller holds are returned,
    so the builder offers exactly the metrics each visible source supports.
    """
    # _load_db_metrics() returns {code: {...}} including format; _accessible_metrics()
    # strips format for the AI catalog. Rebuild from _load_db_metrics filtered by the
    # same source gate so we keep the format field for the builder.
    perms = set(session.get("permissions", []))
    allowed_sources = {s["id"] for s in accessible(_effective_sources(), perms)}
    out = {}
    for m in _load_db_metrics().values():
        sid = m["source_id"]
        if sid not in allowed_sources:
            continue
        out.setdefault(sid, []).append(
            {
                "code": m["code"],
                "label": _metric_label(m),
                "aggregation": m["aggregation"],
                "baseField": m["base_field"],
                "format": m["format"],
                "totalMode": m.get("total_mode", "sum"),
                "anchor": m.get("anchor"),
            }
        )
    return jsonify(out)


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/metrics",
        endpoint="reporting_metrics",
        view_func=api_metrics,
    )
    app.add_url_rule(
        "/api/reporting/field_values",
        endpoint="reporting_field_values",
        view_func=api_field_values,
        methods=["POST"],
    )
