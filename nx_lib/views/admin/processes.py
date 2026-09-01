"""Admin processes: dbo.ProcessSources / ProcessFieldMappings (mapping config),
reads and writes."""

import re

import pyodbc
from flask import current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ... import mapping_config
from ...db import engine_nexora_db
from ...mapping_config import invalidate_mapping_config
from ...security import has_permission, page_visibility, require_permission
from .clients import _CLIENT_CODE_RE


def _process_field_dict(field_mapping):
    return {
        "field_key": field_mapping.field_key,
        "column": field_mapping.column,
        "column_type": field_mapping.column_type,
    }


def _process_source_dict(source, fields):
    return {
        "client": source.client,
        "process": source.process,
        "table": source.table,
        "alias": source.alias,
        "join_condition": source.join_condition,
        "time_filter": source.time_filter,
        "suggestion_time_filter": source.suggestion_time_filter,
        "export_column": source.export_column,
        "import_column": source.import_column,
        "workitem_column": source.workitem_column,
        "extra_condition": source.extra_condition,
        "id_column_type": source.id_column_type,
        "fields": [_process_field_dict(m) for m in fields],
    }


@require_permission("admin.view.processes")
def admin_processes_view():
    """Read-only view of dbo.ProcessSources / ProcessFieldMappings (migration
    0074), grouped by ClientCode -- a *runtime source* (default/ms02, see
    dbo.Clients), not a customer (dbo.Organizations) -- then by ProcessName,
    with each process's field mappings as a nested table. Read entirely
    through the cached nx_lib/mapping_config.py registry, never raw SQL.

    registry() returning None means the config failed to load (a load error
    is never cached) -- render an explicit "unavailable" state rather than an
    empty-looking success. The edit affordances render only for
    admin.edit.processes; the free-form SQL fragment columns (JoinCondition,
    TimeFilter, SuggestionTimeFilter, ExtraCondition) stay read-only for
    everybody -- they are editable only by a migration."""
    reg = mapping_config.registry()
    clients_data = []
    if reg is not None:
        by_client = {}
        for (client, process), source in reg.sources.items():
            fields = sorted(
                (m for m in reg.mappings if m.client == client and m.process == process),
                key=lambda m: m.field_key,
            )
            by_client.setdefault(client, []).append((process, source, fields))
        for client in sorted(by_client):
            processes = sorted(by_client[client], key=lambda item: item[0])
            clients_data.append(
                {
                    "client": client,
                    "processes": [
                        _process_source_dict(source, fields) for _, source, fields in processes
                    ],
                }
            )

    return render_template(
        "admin/processes.html",
        mapping_config_available=reg is not None,
        can_edit=has_permission("admin.edit.processes"),
        clients_data=clients_data,
        client_codes=_client_codes(),
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


@require_permission("admin.view.processes")
def api_admin_processes_list():
    """JSON mirror of admin_processes_view() for a single client (or every
    client when ``?client=`` is omitted) -- read through nx_lib/mapping_config.py,
    never raw SQL. Mirrors that module's fail-closed contract: a registry load
    failure is a 503, never an empty-looking 200 (task 6 brief)."""
    client = request.args.get("client")
    reg = mapping_config.registry()
    if reg is None:
        return jsonify({"error": _("Mapping config is currently unavailable.")}), 503

    sources = mapping_config.sources_for(client)
    processes = []
    for source in sorted(sources, key=lambda s: (s.client, s.process)):
        fields = sorted(
            mapping_config.mappings_for(source.client, [source.process]),
            key=lambda m: m.field_key,
        )
        processes.append(_process_source_dict(source, fields))

    return jsonify({"client": client, "processes": processes})


# --------------------- processes (mapping config, writes) -------------------------- #

# ProcessName MUST be exactly <customer>.<process> -- two dot-separated
# segments, no more, no fewer. This is NOT cosmetic and NOT "convention only":
# every consumer of the auto-provisioned workitems.filter.process.<ProcessName>
# permission reconstructs the process name from the permission code as exactly
# the LAST TWO dot-segments (nx_lib/views/workitems.py, nx_lib/process_helpers.py
# `parts[-2], parts[-1]`). A one-segment name ("Invoice") derives back as
# "process.Invoice" and the grant silently never matches; a three-segment name
# ("acme.eu.01_Invoice") derives back as "eu.01_Invoice", same silent dead end;
# and worse, "x.acme.01_Invoice" reduces to "acme.01_Invoice", so it would
# piggyback on another customer's existing grant. Until this page existed the
# invariant held only because process names were migration-controlled -- now an
# admin types them, so it is enforced here.
_PROCESS_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,49}\.[A-Za-z0-9_\-]{1,50}$")

# FieldKey is a plain mapping key (doctype, invoice_no) -- it is never turned
# into a permission code, so it keeps the looser shape.
_FIELD_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")

# TableName / TableAlias / ColumnName / Export|Import|WorkitemColumn are
# INTERPOLATED into SQL by the downstream query builders (f-strings in
# nx_lib/views/dashboard.py and nx_lib/workitem_sources.py) -- they are config,
# not bind parameters. Every admin-editable field that reaches a builder is
# validated on the way in, here, server-side. Quotes and brackets are allowed
# because the live config holds qualified identifiers in both dialects
# (dbo.tblAlpha, public."DossierStatistik") -- spaces, semicolons, parentheses
# and comment markers are not.
_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_."\[\]]{0,99}$')

# ColumnType / IdColumnType are never interpolated -- they are only compared
# against the literal type buckets in workitems.py / workitem_sources.py (e.g.
# 'nvarchar', 'character varying'), hence the space.
_COLUMN_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]{0,29}$")

# ProcessSources.JoinCondition / TimeFilter / SuggestionTimeFilter /
# ExtraCondition are free-form SQL fragments by design and are deliberately NOT
# writable here: no validator can make an arbitrary predicate safe, so they
# stay migration-only. They appear in no INSERT/UPDATE and in no form below --
# a payload carrying them is ignored, not applied.
_PROCESS_PERMISSION_PREFIX = "workitems.filter.process."


def _validate_identifier_fields(data, fields, errors, *, required=()):
    """Append an error for every ``fields`` entry that is present but is not a
    plain SQL identifier (and for every ``required`` entry that is missing)."""
    for field in fields:
        value = (data.get(field) or "").strip()
        if not value:
            if field in required:
                errors.append(_("%(field)s is required.", field=field))
            continue
        if not _IDENT.match(value):
            errors.append(
                _(
                    "%(field)s must be a plain SQL identifier (letters, digits, "
                    "underscores, dots, quotes or brackets).",
                    field=field,
                )
            )


def _validate_process_identity(client_code, process_name, errors, field_key=None):
    if not _CLIENT_CODE_RE.match(client_code or ""):
        errors.append(_("Client code must be 2-50 lowercase letters, digits or underscores."))
    if not _PROCESS_NAME_RE.match(process_name or ""):
        errors.append(
            _(
                "Process name must be exactly <customer>.<process> -- two parts separated "
                "by a single dot (e.g. acme.01_Invoice), letters, digits, dashes or "
                "underscores only. The permission that grants access to this process is "
                "derived from those two parts, so any other shape can never be granted."
            )
        )
    if field_key is not None and not _FIELD_KEY_RE.match(field_key or ""):
        errors.append(_("Field key must be 1-100 letters, digits, dots, dashes or underscores."))


def _validate_process_source_payload(data, client_code, process_name):
    """Server-side validation for the process-source write endpoints -- never
    trust the client-side checks in templates/js/admin/_processes_js.html."""
    errors = []
    _validate_process_identity(client_code, process_name, errors)
    _validate_identifier_fields(
        data,
        ("TableName", "TableAlias", "ExportColumn", "ImportColumn", "WorkitemColumn"),
        errors,
        required=("TableName",),
    )
    if len((data.get("TableAlias") or "").strip()) > 10:
        errors.append(_("Table alias must be at most 10 characters."))
    id_column_type = (data.get("IdColumnType") or "").strip()
    if id_column_type and not _COLUMN_TYPE_RE.match(id_column_type):
        errors.append(_("Id column type must be a plain SQL type name."))
    return errors


def _validate_field_mapping_payload(data, client_code, process_name, field_key):
    errors = []
    _validate_process_identity(client_code, process_name, errors, field_key=field_key)
    _validate_identifier_fields(data, ("ColumnName",), errors, required=("ColumnName",))
    column_type = (data.get("ColumnType") or "").strip()
    if column_type and not _COLUMN_TYPE_RE.match(column_type):
        errors.append(_("Column type must be a plain SQL type name."))
    return errors


def _process_source_values(data):
    """The six writable ProcessSources columns, in INSERT/UPDATE order. The
    free-form SQL fragment columns are absent on purpose."""
    return (
        (data.get("TableName") or "").strip(),
        (data.get("TableAlias") or "").strip() or None,
        (data.get("ExportColumn") or "").strip() or None,
        (data.get("ImportColumn") or "").strip() or None,
        (data.get("WorkitemColumn") or "").strip() or None,
        (data.get("IdColumnType") or "").strip() or None,
    )


def _validation_error(errors):
    return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), 400


def _permission_reduction(process_name):
    """The (customer, process) pair every consumer derives back out of a
    ``workitems.filter.process.<ProcessName>`` code -- the last two dot
    segments. Two process names sharing a reduction share an entitlement,
    whatever their ClientCode: the permission code carries no client."""
    return ".".join((process_name or "").split(".")[-2:])


def _reduction_conflict(cursor, client_code, process_name):
    """The existing (ClientCode, ProcessName) whose permission reduction
    collides with ``process_name``, or None.

    _PROCESS_NAME_RE already forces new names to two segments, so the new name
    IS its own reduction -- but rows written before this page existed (or by a
    migration) may have more, and a legacy 'x.acme.01_Invoice' reduces onto a
    freshly typed 'acme.01_Invoice'. The exact same pair is not a conflict: the
    PK insert below turns that into the usual 409 "already exists".
    """
    reduction = _permission_reduction(process_name)
    cursor.execute("SELECT ClientCode, ProcessName FROM dbo.ProcessSources")
    for row in cursor.fetchall():
        existing = (row[0], row[1])
        if existing == (client_code, process_name):
            continue
        if _permission_reduction(row[1]) == reduction:
            return existing
    return None


def _client_code_exists(cursor, client_code):
    cursor.execute("SELECT COUNT(*) FROM dbo.Clients WHERE ClientCode = ?", (client_code,))
    row = cursor.fetchone()
    return bool(row and row[0])


def _client_codes():
    """ClientCodes from dbo.Clients, for the /admin/processes picker. Read from
    the table rather than from the resolved CLIENTS registry on purpose: a row
    that is configured but not loaded (missing env keys) is still a legitimate
    target for process config. Degrades to [] -- the picker then falls back to
    free text rather than blocking the page."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ClientCode FROM dbo.Clients ORDER BY ClientCode")
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        current_app.logger.error(f"Failed to fetch client codes: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_process_source_add():
    """Add a dbo.ProcessSources row (migration 0074) AND provision its
    ``workitems.filter.process.<ProcessName>`` permission in the same
    transaction -- self-service onboarding is the whole point of this page, and
    a process nobody can be granted is a half-created process.

    The permission is created granted to NOBODY: granting stays a deliberate
    act at /admin/access-control. The insert mirrors migration 0059's
    idempotent WHERE NOT EXISTS shape, so re-adding a process whose permission
    row outlived an earlier delete is a no-op rather than a unique-key error."""
    data = request.get_json() or {}
    client_code = (data.get("ClientCode") or "").strip()
    process_name = (data.get("ProcessName") or "").strip()
    errors = _validate_process_source_payload(data, client_code, process_name)
    if errors:
        return _validation_error(errors)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        # Nothing in the schema ties ProcessSources.ClientCode to dbo.Clients
        # (migration 0079 deliberately adds no FK -- ProcessSources predates the
        # table), so a typo like 'defualt' would otherwise create a process
        # source, auto-provision its permission, and yield config that can never
        # resolve. Check it here instead.
        if not _client_code_exists(cursor, client_code):
            return _validation_error(
                [
                    _(
                        "Unknown client code %(code)s -- it must be an existing "
                        "runtime source from the Clients page.",
                        code=client_code,
                    )
                ]
            )
        conflict = _reduction_conflict(cursor, client_code, process_name)
        if conflict:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": _(
                            "Process name %(name)s collides with the existing "
                            "%(other_client)s / %(other)s: both resolve to the same "
                            "permission %(code)s, so a grant for one would entitle the "
                            "other. Pick a different name.",
                            name=process_name,
                            other_client=conflict[0],
                            other=conflict[1],
                            code=f"{_PROCESS_PERMISSION_PREFIX}{_permission_reduction(process_name)}",
                        ),
                    }
                ),
                409,
            )
        cursor.execute(
            "INSERT INTO dbo.ProcessSources (ClientCode, ProcessName, TableName, TableAlias, "
            "ExportColumn, ImportColumn, WorkitemColumn, IdColumnType) VALUES (?,?,?,?,?,?,?,?)",
            (client_code, process_name, *_process_source_values(data)),
        )
        code = f"{_PROCESS_PERMISSION_PREFIX}{process_name}"
        cursor.execute(
            "INSERT INTO dbo.Permission (Code, Description) SELECT ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = ?)",
            (code, f"View {process_name} workitems"[:200], code),
        )
        conn.commit()
        invalidate_mapping_config()
        return jsonify(
            {
                "success": True,
                "message": _(
                    "Process source created. Its permission %(code)s was created but "
                    "granted to nobody -- grant it under Access Control.",
                    code=code,
                ),
            }
        )
    except pyodbc.IntegrityError:
        return (
            jsonify({"success": False, "message": _("This process source already exists.")}),
            409,
        )
    except Exception as e:
        current_app.logger.error(f"Error adding process source {client_code}/{process_name}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_process_source_edit(clientcode, processname):
    """Edit the identifier columns of a dbo.ProcessSources row. Identity
    (ClientCode, ProcessName) comes from the URL and is never rewritten -- a
    rename would strand the process's field mappings and its permission."""
    data = request.get_json() or {}
    errors = _validate_process_source_payload(data, clientcode, processname)
    if errors:
        return _validation_error(errors)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.ProcessSources SET TableName=?, TableAlias=?, ExportColumn=?, "
            "ImportColumn=?, WorkitemColumn=?, IdColumnType=? "
            "WHERE ClientCode=? AND ProcessName=?",
            (*_process_source_values(data), clientcode, processname),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Process source not found.")}), 404
        invalidate_mapping_config()
        return jsonify({"success": True, "message": _("Process source updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error editing process source {clientcode}/{processname}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_process_source_delete(clientcode, processname):
    """Delete a dbo.ProcessSources row. Refused with 409 while field mappings
    still reference it -- FK_ProcessFieldMappings_ProcessSources would raise
    anyway, and a 500 tells the admin nothing about what to do next.

    The ``workitems.filter.process.<name>`` permission row is deliberately left
    behind: dropping it would silently revoke access the admin never asked to
    change, and re-adding the process re-uses it (see the add endpoint)."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM dbo.ProcessFieldMappings WHERE ClientCode = ? "
            "AND ProcessName = ?",
            (clientcode, processname),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": _(
                            "This process source still has field mappings and cannot be "
                            "deleted. Remove them first."
                        ),
                    }
                ),
                409,
            )

        cursor.execute(
            "DELETE FROM dbo.ProcessSources WHERE ClientCode=? AND ProcessName=?",
            (clientcode, processname),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Process source not found.")}), 404
        invalidate_mapping_config()
        return jsonify({"success": True, "message": _("Process source deleted successfully.")})
    except pyodbc.IntegrityError:
        return (
            jsonify(
                {
                    "success": False,
                    "message": _("This process source is still referenced and cannot be deleted."),
                }
            ),
            409,
        )
    except Exception as e:
        current_app.logger.error(f"Error deleting process source {clientcode}/{processname}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_field_mapping_add():
    """Add a dbo.ProcessFieldMappings row -- one doc-field of one process."""
    data = request.get_json() or {}
    client_code = (data.get("ClientCode") or "").strip()
    process_name = (data.get("ProcessName") or "").strip()
    field_key = (data.get("FieldKey") or "").strip()
    errors = _validate_field_mapping_payload(data, client_code, process_name, field_key)
    if errors:
        return _validation_error(errors)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.ProcessFieldMappings (ClientCode, ProcessName, FieldKey, "
            "ColumnName, ColumnType) VALUES (?,?,?,?,?)",
            (
                client_code,
                process_name,
                field_key,
                (data.get("ColumnName") or "").strip(),
                (data.get("ColumnType") or "").strip() or None,
            ),
        )
        conn.commit()
        invalidate_mapping_config()
        return jsonify({"success": True, "message": _("Field mapping created successfully.")})
    except pyodbc.IntegrityError:
        # PK_ProcessFieldMappings, or FK_ProcessFieldMappings_ProcessSources
        # when the parent process source does not exist.
        return (
            jsonify(
                {
                    "success": False,
                    "message": _(
                        "This field mapping already exists, or its process source does not."
                    ),
                }
            ),
            409,
        )
    except Exception as e:
        current_app.logger.error(f"Error adding field mapping {client_code}/{process_name}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_field_mapping_edit(clientcode, processname, fieldkey):
    """Edit a field mapping's column. Identity comes from the URL -- renaming a
    FieldKey is a delete plus an add, not an update."""
    data = request.get_json() or {}
    errors = _validate_field_mapping_payload(data, clientcode, processname, fieldkey)
    if errors:
        return _validation_error(errors)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.ProcessFieldMappings SET ColumnName=?, ColumnType=? "
            "WHERE ClientCode=? AND ProcessName=? AND FieldKey=?",
            (
                (data.get("ColumnName") or "").strip(),
                (data.get("ColumnType") or "").strip() or None,
                clientcode,
                processname,
                fieldkey,
            ),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Field mapping not found.")}), 404
        invalidate_mapping_config()
        return jsonify({"success": True, "message": _("Field mapping updated successfully.")})
    except Exception as e:
        current_app.logger.error(
            f"Error editing field mapping {clientcode}/{processname}/{fieldkey}: {e}"
        )
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.edit.processes")
def api_admin_field_mapping_delete(clientcode, processname, fieldkey):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dbo.ProcessFieldMappings WHERE ClientCode=? AND ProcessName=? "
            "AND FieldKey=?",
            (clientcode, processname, fieldkey),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Field mapping not found.")}), 404
        invalidate_mapping_config()
        return jsonify({"success": True, "message": _("Field mapping deleted successfully.")})
    except Exception as e:
        current_app.logger.error(
            f"Error deleting field mapping {clientcode}/{processname}/{fieldkey}: {e}"
        )
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/admin/processes", endpoint="admin_processes_view", view_func=admin_processes_view
    )
    app.add_url_rule(
        "/api/admin/processes/list",
        endpoint="api_admin_processes_list",
        view_func=api_admin_processes_list,
    )
    app.add_url_rule(
        "/admin/processes/sources/add",
        endpoint="api_admin_process_source_add",
        view_func=api_admin_process_source_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/processes/sources/edit/<clientcode>/<processname>",
        endpoint="api_admin_process_source_edit",
        view_func=api_admin_process_source_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/processes/sources/delete/<clientcode>/<processname>",
        endpoint="api_admin_process_source_delete",
        view_func=api_admin_process_source_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/admin/processes/fields/add",
        endpoint="api_admin_field_mapping_add",
        view_func=api_admin_field_mapping_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/processes/fields/edit/<clientcode>/<processname>/<fieldkey>",
        endpoint="api_admin_field_mapping_edit",
        view_func=api_admin_field_mapping_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/processes/fields/delete/<clientcode>/<processname>/<fieldkey>",
        endpoint="api_admin_field_mapping_delete",
        view_func=api_admin_field_mapping_delete,
        methods=["DELETE"],
    )
