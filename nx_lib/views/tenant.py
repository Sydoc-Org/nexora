"""Tenant kernel: the parametrized ``/t/<tenant_code>/<page_key>`` route family.

One route family serves every tenant's generated list/CRUD pages from the
cached registry (``nx_lib/tenant/registry.py``, Task 2) and the
descriptor->SQL builders (``nx_lib/tenant/queries.py``, Task 3) -- no
per-tenant view code, no Blueprints (house rule: routes register via
``add_url_rule`` so every ``url_for(...)`` in templates keeps working
unchanged). Permission is dynamic -- the tenant code lives in the URL, so the
permission code (``tenant.<code>.view`` / ``.edit``) is dynamic too -- so it
is checked *inside* each view, never via ``@require_permission``, which only
ever takes a static string literal.

Security invariant this module owns (carried from Task 3's dispatch note):
``queries.py``'s filter/sort column names are identifier-valid but never
cross-checked against the entity's actual field list -- that module's own
docstring says so. Every filter/sort column accepted from a query string here
is drawn from ``fields_for(tenant_code, entity_key)`` first
(``_parse_filters``'s ``fields_by_column`` / ``_parse_sort``'s
``allowed_columns``, both built from the registry's own visible-field list for
this entity) -- an unrecognised query-string column name is silently
dropped, never passed through to ``build_list_query``.
"""

import io
from datetime import date

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..clients import CLIENTS
from ..i18n import get_locale
from ..security import PermissionDenied, has_permission, page_visibility
from ..tenant import entity_for, fields_for, pages_for, registry, tenant
from ..tenant.queries import build_delete, build_insert, build_list_query, build_update

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_EXPORT_MAX_ROWS = 10000  # bound an export so a huge/malicious box can't hang a worker

# Default filter operator by SemanticRole -- text-ish roles get a substring
# match, everything else an exact match. Date fields are handled separately
# (a _from/_to range, not a single filter_<column> value) in _parse_filters.
_FILTER_ROLE_OP = {
    "text": "contains",
    "category": "contains",
    "person": "contains",
    "identifier": "eq",
    "money": "eq",
    "count": "eq",
    "flag": "eq",
}


# ---------------------------------------------------------------- helpers --


def _engine_for_role(client, role):
    if role == "stats":
        return client.stats_engine
    if role == "docfields":
        return client.docfields_engine
    return client.runtime_engine


def _dialect_for_role(client, role):
    if role == "stats":
        return client.stats_dialect
    if role == "docfields":
        return client.docfields_dialect
    return client.dialect


def _resolve_client_engine(t, entity):
    """(engine, dialect) for ``entity``'s ``engine_role`` on tenant ``t``'s
    client -- ``(None, None)`` when the client row itself or its engine for
    that role is unavailable (K3: engines resolve via import-time CLIENTS,
    same degrade-to-None contract as every other engine in this codebase)."""
    client = CLIENTS.get(t.client_code)
    if client is None:
        return None, None
    engine = _engine_for_role(client, entity.engine_role)
    if engine is None:
        return None, None
    return engine, _dialect_for_role(client, entity.engine_role)


def _resolve_page_entity(tenant_code, page_key, *, require_entries=False):
    """(tenant, page, entity, visible_fields) for (tenant_code, page_key), or
    aborts 404 -- unknown tenant/page, a custom page (no entity), a page whose
    entity row is missing, or (when ``require_entries``) an entity whose Kind
    isn't 'entries' (documents/lookup boxes are read/CRUD-linked, never
    row-written directly -- CRUD is entries-only)."""
    t = tenant(tenant_code)
    pages = pages_for(tenant_code)
    page = next((p for p in pages if p.key == page_key), None)
    if t is None or page is None or page.page_type == "custom" or not page.entity:
        abort(404)
    entity = entity_for(tenant_code, page.entity)
    if entity is None:
        abort(404)
    if require_entries and entity.kind != "entries":
        abort(404)
    fields = [f for f in fields_for(tenant_code, page.entity) if f.visible]
    return t, page, entity, fields


def _writable_columns(entity, fields):
    """Visible, non-id columns -- mirrors queries.py's own private helper of
    the same name so the write column list here is always in lockstep with
    what build_insert/build_update actually bind values to."""
    return [f.column for f in fields if f.visible and f.column != entity.id_column]


def _parse_date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _coerce_record_id(raw):
    """Best-effort int coercion for a path-segment record id -- most box id
    columns are numeric (identity/serial); postgres in particular does not
    implicitly cast a string parameter against an integer column. A
    non-numeric id (e.g. a natural string key) passes through unchanged."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def _parse_filters(args, fields_by_column):
    """[(column, op, value)] from ``?filter_<column>=...`` query params --
    only for columns present in ``fields_by_column`` (the entity's own
    visible fields; see module docstring). A date field uses a
    ``filter_<column>_from`` / ``_to`` range instead of a single value; a
    value that fails to parse is dropped silently (degrades to "no filter"
    rather than 400ing the whole list for one bad query param)."""
    filters = []
    for column, field in fields_by_column.items():
        if field.semantic_role == "date":
            date_from = args.get(f"filter_{column}_from")
            if date_from:
                parsed = _parse_date(date_from)
                if parsed is not None:
                    filters.append((column, "gte", parsed.isoformat()))
            date_to = args.get(f"filter_{column}_to")
            if date_to:
                parsed = _parse_date(date_to)
                if parsed is not None:
                    filters.append((column, "lt", parsed.isoformat()))
            continue
        value = args.get(f"filter_{column}")
        if not value:
            continue
        op = _FILTER_ROLE_OP.get(field.semantic_role, "contains")
        filters.append((column, op, value))
    return filters


def _parse_sort(args, allowed_columns):
    """(column, direction) from ``?sort=<column>&dir=asc|desc``, or None --
    ``column`` must be in ``allowed_columns`` (the entity's visible fields
    plus its id column; see module docstring), otherwise the request falls
    back to build_list_query's own default order."""
    column = args.get("sort")
    if not column or column not in allowed_columns:
        return None
    direction = args.get("dir", "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"
    return (column, direction)


def _parse_pagination(args):
    try:
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(args.get("limit", _DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT
    return max(0, offset), max(1, min(limit, _MAX_LIMIT))


def _validate_values(entity, fields, data):
    """(values, errors) for entity's writable columns -- each raw JSON value
    is converted/validated by its field's SemanticRole: 'date' -> ISO date
    parse, 'money'/'count' -> numeric, anything else -> text. ``errors`` is a
    list of translated messages; empty means every value converted cleanly
    and ``values`` has one entry per writable column."""
    fields_by_column = {f.column: f for f in fields}
    values = {}
    errors = []
    for column in _writable_columns(entity, fields):
        field = fields_by_column[column]
        label = field.labels.get("en") or column
        if column not in data:
            errors.append(_("Missing value for %(field)s.", field=label))
            continue
        raw = data[column]
        role = field.semantic_role
        if role == "date":
            parsed = _parse_date(raw)
            if parsed is None:
                errors.append(_("%(field)s must be a valid date (YYYY-MM-DD).", field=label))
            else:
                values[column] = parsed.isoformat()
        elif role in ("money", "count"):
            try:
                values[column] = int(raw) if role == "count" else float(raw)
            except (TypeError, ValueError):
                errors.append(_("%(field)s must be numeric.", field=label))
        else:
            values[column] = "" if raw is None else str(raw)
    return values, errors


def visible_tenant_nav() -> list[dict]:
    """[{"code", "label", "pages": [...]}] for every tenant the current
    session holds ``tenant.<code>.view`` for -- [] when the registry itself
    is unavailable (never a partial/unsafe result, same fail-closed contract
    as the registry module itself). Consumed by Task 6's sidebar nav context
    processor; each page entry carries enough to build its own link
    (list/crud pages link ``tenant_page``, custom pages link their layout
    endpoint)."""
    reg = registry()
    if reg is None:
        return []
    nav = []
    for code in sorted(reg.tenants):
        t = reg.tenants[code]
        if not has_permission(f"tenant.{code}.view"):
            continue
        nav.append(
            {
                "code": t.code,
                "label": t.display_name,
                "pages": [
                    {
                        "key": p.key,
                        "page_type": p.page_type,
                        "endpoint": (
                            (p.layout or {}).get("endpoint") if p.page_type == "custom" else None
                        ),
                    }
                    for p in pages_for(code)
                ],
            }
        )
    return nav


# -------------------------------------------------------------------- page --


def tenant_page(tenant_code, page_key):
    if not has_permission(f"tenant.{tenant_code}.view"):
        raise PermissionDenied()

    reg = registry()
    if reg is None:
        # A load failure is never cached (nx_lib/tenant/registry.py) -- render
        # the explicit unavailable state, never an empty-looking page (same
        # contract as admin_processes_view's mapping_config_available flag).
        return render_template(
            "tenant/page.html",
            unavailable=True,
            tenant=None,
            page=None,
            entity=None,
            fields=[],
            tenant_code=tenant_code,
            page_key=page_key,
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )

    t = tenant(tenant_code)
    pages = pages_for(tenant_code)
    page = next((p for p in pages if p.key == page_key), None)
    if t is None or page is None:
        abort(404)

    if page.page_type == "custom":
        endpoint = (page.layout or {}).get("endpoint")
        return redirect(url_for(endpoint)) if endpoint else abort(404)

    entity = entity_for(tenant_code, page.entity) if page.entity else None
    if entity is None:
        abort(404)
    fields = [f for f in fields_for(tenant_code, page.entity) if f.visible]

    # Built here, not in the template: Jinja's expression language has no
    # list-comprehension syntax, only the {% for %} statement tag.
    locale = get_locale() or "en"
    header_columns = [{"label": entity.id_column}] + [
        {"label": f.labels.get(locale) or f.labels.get("en") or f.column}
        for f in fields
        if f.column != entity.id_column
    ]

    return render_template(
        "tenant/page.html",
        unavailable=False,
        tenant=t,
        page=page,
        entity=entity,
        fields=fields,
        header_columns=header_columns,
        tenant_code=tenant_code,
        page_key=page_key,
        can_edit=has_permission(f"tenant.{tenant_code}.edit"),
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


# --------------------------------------------------------------------- api --


def api_tenant_list(tenant_code, page_key):
    if not has_permission(f"tenant.{tenant_code}.view"):
        raise PermissionDenied()

    t, _page, entity, fields = _resolve_page_entity(tenant_code, page_key)
    engine, dialect = _resolve_client_engine(t, entity)
    if engine is None:
        return jsonify({"success": False, "unavailable": True}), 503

    fields_by_column = {f.column: f for f in fields}
    allowed_columns = set(fields_by_column) | {entity.id_column}
    filters = _parse_filters(request.args, fields_by_column)
    sort = _parse_sort(request.args, allowed_columns)
    offset, limit = _parse_pagination(request.args)

    count_sql, page_sql, (count_params, page_params) = build_list_query(
        entity, fields, dialect, filters=filters, sort=sort, offset=offset, limit=limit
    )

    conn = None
    cursor = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute(count_sql, count_params)
        total_row = cursor.fetchone()
        total = total_row[0] if total_row else 0
        cursor.execute(page_sql, page_params)
        cols = [c[0] for c in cursor.description]
        rows = [dict(zip(cols, r, strict=False)) for r in cursor.fetchall()]
    except Exception as e:
        current_app.logger.error(f"tenant list query failed for {tenant_code}/{page_key}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    locale = get_locale() or "en"
    field_meta = [
        {
            "column": f.column,
            "label": f.labels.get(locale) or f.labels.get("en") or f.column,
            "semantic_role": f.semantic_role,
        }
        for f in fields
    ]

    return jsonify(
        {
            "success": True,
            "total": total,
            "offset": offset,
            "limit": limit,
            "id_column": entity.id_column,
            "fields": field_meta,
            "rows": rows,
        }
    )


def api_tenant_add(tenant_code, page_key):
    if not has_permission(f"tenant.{tenant_code}.edit"):
        raise PermissionDenied()

    t, _page, entity, fields = _resolve_page_entity(tenant_code, page_key, require_entries=True)
    engine, dialect = _resolve_client_engine(t, entity)
    if engine is None:
        return jsonify({"success": False, "unavailable": True}), 503

    columns = _writable_columns(entity, fields)
    if not columns:
        return jsonify({"success": False, "message": _("This entity has no writable fields.")}), 400

    data = request.get_json(silent=True) or {}
    values, errors = _validate_values(entity, fields, data)
    if errors:
        return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), 400

    insert_sql = build_insert(entity, fields, dialect)
    conn = None
    cursor = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute(insert_sql, [values[c] for c in columns])
        conn.commit()
        return jsonify({"success": True, "message": _("Record created successfully.")})
    except Exception as e:
        current_app.logger.error(f"tenant add failed for {tenant_code}/{page_key}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def api_tenant_edit(tenant_code, page_key, record_id):
    if not has_permission(f"tenant.{tenant_code}.edit"):
        raise PermissionDenied()

    t, _page, entity, fields = _resolve_page_entity(tenant_code, page_key, require_entries=True)
    engine, dialect = _resolve_client_engine(t, entity)
    if engine is None:
        return jsonify({"success": False, "unavailable": True}), 503

    columns = _writable_columns(entity, fields)
    if not columns:
        return jsonify({"success": False, "message": _("This entity has no writable fields.")}), 400

    data = request.get_json(silent=True) or {}
    values, errors = _validate_values(entity, fields, data)
    if errors:
        return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), 400

    update_sql = build_update(entity, fields, dialect)
    params = [values[c] for c in columns] + [_coerce_record_id(record_id)]
    conn = None
    cursor = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute(update_sql, params)
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Record not found.")}), 404
        return jsonify({"success": True, "message": _("Record updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"tenant edit failed for {tenant_code}/{page_key}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def api_tenant_delete(tenant_code, page_key, record_id):
    if not has_permission(f"tenant.{tenant_code}.edit"):
        raise PermissionDenied()

    t, _page, entity, _fields = _resolve_page_entity(tenant_code, page_key, require_entries=True)
    engine, dialect = _resolve_client_engine(t, entity)
    if engine is None:
        return jsonify({"success": False, "unavailable": True}), 503

    delete_sql = build_delete(entity, dialect)
    conn = None
    cursor = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute(delete_sql, [_coerce_record_id(record_id)])
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Record not found.")}), 404
        return jsonify({"success": True, "message": _("Record deleted successfully.")})
    except Exception as e:
        current_app.logger.error(f"tenant delete failed for {tenant_code}/{page_key}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def api_tenant_export(tenant_code, page_key):
    if not has_permission(f"tenant.{tenant_code}.view"):
        raise PermissionDenied()

    t, page, entity, fields = _resolve_page_entity(tenant_code, page_key)
    engine, dialect = _resolve_client_engine(t, entity)
    if engine is None:
        return jsonify({"success": False, "unavailable": True}), 503

    fields_by_column = {f.column: f for f in fields}
    allowed_columns = set(fields_by_column) | {entity.id_column}
    filters = _parse_filters(request.args, fields_by_column)
    sort = _parse_sort(request.args, allowed_columns)

    _count_sql, page_sql, (_count_params, page_params) = build_list_query(
        entity, fields, dialect, filters=filters, sort=sort, offset=0, limit=_EXPORT_MAX_ROWS
    )

    conn = None
    cursor = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        cursor.execute(page_sql, page_params)
        cols = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"tenant export query failed for {tenant_code}/{page_key}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    import openpyxl  # local import: openpyxl is heavyish and only used here (mirrors
    # workitem_sources.parse_prepared_xlsx's own local import)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (page.key or "Export")[:31]

    header_cols = [entity.id_column] + [f.column for f in fields if f.column != entity.id_column]
    locale = get_locale() or "en"
    header_labels = [entity.id_column] + [
        (f.labels.get(locale) or f.labels.get("en") or f.column)
        for f in fields
        if f.column != entity.id_column
    ]
    ws.append(header_labels)
    for row in rows:
        row_map = dict(zip(cols, row, strict=False))
        ws.append([row_map.get(c) for c in header_cols])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return send_file(
        buf,
        max_age=0,  # private tenant data -- never cache (tests/unit/test_static_v_lint.py)
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{tenant_code}_{page_key}.xlsx",
    )


def register_routes(app):
    app.add_url_rule("/t/<tenant_code>/<page_key>", endpoint="tenant_page", view_func=tenant_page)
    app.add_url_rule(
        "/api/t/<tenant_code>/<page_key>",
        endpoint="api_tenant_list",
        view_func=api_tenant_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/t/<tenant_code>/<page_key>",
        endpoint="api_tenant_add",
        view_func=api_tenant_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/t/<tenant_code>/<page_key>/export",
        endpoint="api_tenant_export",
        view_func=api_tenant_export,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/t/<tenant_code>/<page_key>/<record_id>",
        endpoint="api_tenant_edit",
        view_func=api_tenant_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/t/<tenant_code>/<page_key>/<record_id>",
        endpoint="api_tenant_delete",
        view_func=api_tenant_delete,
        methods=["DELETE"],
    )
