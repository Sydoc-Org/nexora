"""Admin clients: dbo.Clients CRUD (runtime sources -- default/ms02, not
customers, see dbo.Organizations)."""

import re

import pyodbc
from flask import current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ... import clients as clients_registry
from ...clients import _ENGINE_KEYS
from ...db import engine_nexora_db
from ...security import has_permission, page_visibility, require_permission


@require_permission("admin.clients.view")
def admin_clients_view():
    """List of dbo.Clients -- runtime sources (default/ms02), not customers
    (see dbo.Organizations). The add/edit/delete affordances are rendered only
    for ``admin.clients.edit`` (``can_edit``); the endpoints re-check it."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ClientCode, DisplayName, Dialect, RuntimeEngineKey, StatsEngineKey, "
            "StatsDialect, DocfieldsEngineKey, DocfieldsDialect, OctoDomain, SecretRef, "
            "IsActive FROM dbo.Clients ORDER BY ClientCode"
        )
        clients = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        # Configured state (the table) is not resolved state (what the process
        # actually runs on). 0079's seed is unconditional, so PROD gets an
        # 'ms02' row whether or not env/PROD.env carries the MS02_* keys -- and
        # without them _build_clients() skips it, leaving the page cheerfully
        # reporting "Active: Yes" for a runtime that does not exist. Mark each
        # row with whether the live registry actually holds it.
        for client in clients:
            client["loaded"] = client.get("ClientCode") in clients_registry.CLIENTS

        return render_template(
            "admin/clients.html",
            clients=clients,
            registry_degraded_reason=clients_registry.REGISTRY_DEGRADED_REASON,
            can_edit=has_permission("admin.clients.edit"),
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to fetch clients: {e}")
        return render_template("handlers/500.html"), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


_CLIENTS_ALLOWED_DIALECTS = {"tsql", "postgres"}
_CLIENT_CODE_RE = re.compile(r"^[a-z0-9_]{2,50}$")
# SecretRef holds only an env-key *prefix* (e.g. "MS02"), never a secret value
# -- cfg.py looks up f"{SecretRef}_OCTO_CLIENT_SECRET" etc. This shape check is
# the cheap guard called for: it rejects anything that isn't prefix-shaped
# (lower-case, spaces, punctuation -- the kind of thing a pasted secret has),
# not a guarantee that a value can never sneak in.
_SECRET_REF_RE = re.compile(r"^[A-Z0-9_]{0,20}$")


def _validate_client_payload(data, *, require_code):
    """Server-side validation for the client add/edit endpoints -- never trust
    the client-side checks in _clients_js.html. Returns a list of error
    messages (empty when the payload is valid)."""
    errors = []

    client_code = (data.get("ClientCode") or "").strip()
    if (require_code or client_code) and not _CLIENT_CODE_RE.match(client_code):
        errors.append(_("Client code must be 2-50 lowercase letters, digits or underscores."))

    if not (data.get("DisplayName") or "").strip():
        errors.append(_("Display name is required."))

    allowed = ", ".join(sorted(_CLIENTS_ALLOWED_DIALECTS))
    dialect = data.get("Dialect")
    if dialect not in _CLIENTS_ALLOWED_DIALECTS:
        errors.append(_("Dialect must be one of: %(allowed)s", allowed=allowed))
    for field in ("StatsDialect", "DocfieldsDialect"):
        value = data.get(field)
        if value and value not in _CLIENTS_ALLOWED_DIALECTS:
            errors.append(_("%(field)s must be one of: %(allowed)s", field=field, allowed=allowed))

    if data.get("RuntimeEngineKey") not in _ENGINE_KEYS:
        errors.append(_("Unknown runtime engine key."))
    for field in ("StatsEngineKey", "DocfieldsEngineKey"):
        value = data.get(field)
        if value and value not in _ENGINE_KEYS:
            errors.append(_("Unknown %(field)s.", field=field))

    secret_ref = data.get("SecretRef")
    if secret_ref and not _SECRET_REF_RE.match(secret_ref):
        errors.append(
            _(
                "Secret ref must be an env-key prefix (upper-case letters, digits, "
                "underscores) -- never a secret value."
            )
        )

    return errors


@require_permission("admin.clients.edit")
def api_admin_clients_add():
    """Add a dbo.Clients row (migration 0079) -- a runtime source (default/
    ms02: which DB/dialect/Octo tenant serves a client), not a customer
    (dbo.Organizations). CLIENTS is built once at import (nx_lib/clients.py),
    so a new row needs an app-pool recycle before it is picked up."""
    data = request.get_json() or {}
    errors = _validate_client_payload(data, require_code=True)
    if errors:
        return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.Clients (ClientCode, DisplayName, Dialect, RuntimeEngineKey, "
            "StatsEngineKey, StatsDialect, DocfieldsEngineKey, DocfieldsDialect, OctoDomain, "
            "SecretRef, IsActive) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                data["ClientCode"].strip(),
                data["DisplayName"].strip(),
                data["Dialect"],
                data["RuntimeEngineKey"],
                data.get("StatsEngineKey") or None,
                data.get("StatsDialect") or None,
                data.get("DocfieldsEngineKey") or None,
                data.get("DocfieldsDialect") or None,
                data.get("OctoDomain") or None,
                data.get("SecretRef") or None,
                1 if data.get("IsActive", True) else 0,
            ),
        )
        conn.commit()
        return jsonify({"success": True, "message": _("Client created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({"success": False, "message": _("Client code already exists.")}), 409
    except Exception as e:
        current_app.logger.error(f"Error adding client: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.clients.edit")
def api_admin_clients_edit(clientcode):
    data = request.get_json() or {}
    errors = _validate_client_payload(data, require_code=False)
    if errors:
        return jsonify({"success": False, "message": " ".join(str(e) for e in errors)}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.Clients SET DisplayName=?, Dialect=?, RuntimeEngineKey=?, "
            "StatsEngineKey=?, StatsDialect=?, DocfieldsEngineKey=?, DocfieldsDialect=?, "
            "OctoDomain=?, SecretRef=?, IsActive=? WHERE ClientCode=?",
            (
                data["DisplayName"].strip(),
                data["Dialect"],
                data["RuntimeEngineKey"],
                data.get("StatsEngineKey") or None,
                data.get("StatsDialect") or None,
                data.get("DocfieldsEngineKey") or None,
                data.get("DocfieldsDialect") or None,
                data.get("OctoDomain") or None,
                data.get("SecretRef") or None,
                1 if data.get("IsActive", True) else 0,
                clientcode,
            ),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Client not found.")}), 404

        return jsonify({"success": True, "message": _("Client updated successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error editing client {clientcode}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@require_permission("admin.clients.edit")
def api_admin_clients_delete(clientcode):
    """Refuses (409) a ClientCode still referenced by dbo.ProcessSources (migration
    0074) instead of deleting it out from under the mapping-config registry
    (nx_lib/mapping_config.py) or the running CLIENTS registry."""
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM dbo.ProcessSources WHERE ClientCode = ?", (clientcode,)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": _(
                            "This client is still referenced by process sources and "
                            "cannot be deleted."
                        ),
                    }
                ),
                409,
            )

        cursor.execute("DELETE FROM dbo.Clients WHERE ClientCode=?", (clientcode,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Client not found.")}), 404

        return jsonify({"success": True, "message": _("Client deleted successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error deleting client {clientcode}: {e}")
        return jsonify({"success": False, "message": _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/admin/clients", endpoint="admin_clients_view", view_func=admin_clients_view)
    app.add_url_rule(
        "/admin/clients/add",
        endpoint="api_admin_clients_add",
        view_func=api_admin_clients_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/clients/edit/<clientcode>",
        endpoint="api_admin_clients_edit",
        view_func=api_admin_clients_edit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/admin/clients/delete/<clientcode>",
        endpoint="api_admin_clients_delete",
        view_func=api_admin_clients_delete,
        methods=["DELETE"],
    )
