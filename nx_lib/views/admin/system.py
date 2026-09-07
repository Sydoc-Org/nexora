"""Admin system: status page, dev server restart, maintenance banner."""

import os
import subprocess

from flask import abort, current_app, jsonify, render_template, request, session
from flask_babel import gettext as _

from ... import clients as clients_registry
from ... import status
from ...config import DOTENV_KEYS, IS_PROD, REPO_ROOT
from ...db import engine_nexora_db
from ...maintenance import (
    _MAINTENANCE_BLOCK_CACHE,
    _get_blocking_maintenance,
    _maintenance_parse_payload,
    _maintenance_row_to_dict,
)
from ...security import has_permission, page_visibility, require_permission

# ----------------------------------- status page ---------------------------------- #


@require_permission("admin.status.view")
def admin_status_view():
    """Component health + incident history, as recorded by ops/outage_monitor.py.

    Deliberately reads only what the monitor persisted (issue #167) instead of
    probing on page load: the point of the page is "what has been true since
    yesterday evening", which a request-scoped ping cannot answer. When the
    monitor has not reported recently the page says so rather than rendering a
    reassuring all-green grid from stale rows.
    """
    try:
        data = status.load_status(
            engine_nexora_db,
            maintenance=_get_blocking_maintenance() is not None,
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load status page data: {e}")
        return render_template("handlers/500.html"), 500
    return render_template(
        "admin/status.html",
        status=data,
        # Import-time degradation of the client registry (nx_lib/clients.py):
        # its only other signal is a logger.error that fires before Flask has
        # configured logging, so it never reaches app.log.
        clients_registry_degraded_reason=clients_registry.REGISTRY_DEGRADED_REASON,
        stale_after_min=status.DEFAULT_STALE_AFTER_S // 60,
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


# ----------------------------------- dev server restart ---------------------------------- #


_SWITCHABLE_ENVS = {"INT", "STAGING"}


def _restart_allowed():
    """May this caller restart / env-switch the dev server?

    The ``admin.server.restart`` permission lives in NexoraDB, and STAGING resolves
    NexoraDB to the prod server (DB_SERVER_PRD) where the row from migration
    0059 doesn't exist — so on STAGING the control vanished and the env switch
    was one-way (#198). Loopback callers are therefore allowed regardless of the
    permission, the same trust rule the /dev/* routes use (#193). PROD is out
    either way: it's IIS-hosted, where restarting means recycling the app pool.
    """
    if IS_PROD:
        return False
    return has_permission("admin.server.restart") or request.remote_addr in ("127.0.0.1", "::1")


def api_admin_restart():
    """Restart the local dev server process (issue #184). Dev-only — 404s on PROD
    since PROD is IIS-hosted and restarting there means recycling the app pool,
    not killing a `python nx_main.py` process. Fires bin/nx.ps1 -r as a hidden
    background process; it kills this process and starts a fresh one, so the response has
    to make it back to the browser before that happens (nx.ps1 sleeps ~1s first).

    Optional JSON body {"env": "INT"|"STAGING"} switches ENVIRONMENT on the way
    back up (issue #187) via nx.ps1's existing --env: flag — PROD is refused by
    nx.ps1 itself, so no need to re-check it here."""
    if IS_PROD:
        abort(404)
    if not _restart_allowed():
        abort(403)
    target_env = (request.get_json(silent=True) or {}).get("env")
    if target_env is not None and target_env not in _SWITCHABLE_ENVS:
        return jsonify({"success": False, "message": _("Unknown environment.")}), 400
    args = ["pwsh", "-File", str(REPO_ROOT / "bin" / "nx.ps1"), "-r"]
    if target_env:
        args.append(f"--env:{target_env}")
    # restart the instance we're actually serving from — without this a
    # --no-conflict instance's restart button would kill the port-8000 one
    args.append(f"--port:{request.environ.get('SERVER_PORT', '8000')}")
    subprocess.Popen(
        args,
        cwd=str(REPO_ROOT),
        # Strip the keys load_dotenv injected into this process: inherited,
        # they'd win over the target env file in the new server (override=False)
        # and it would run INT DB connections while claiming to be STAGING.
        env={k: v for k, v in os.environ.items() if k not in DOTENV_KEYS},
        # CREATE_NO_WINDOW, not DETACHED_PROCESS: pwsh exits 0 without running
        # the script when it has no console at all (#187); a hidden console
        # works and still survives this process being killed by nx.ps1.
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    return jsonify({"success": True})


# ----------------------------------- maintenance banner ---------------------------------- #


@require_permission("admin.maintenance.view")
def admin_maintenance_view():
    try:
        return render_template(
            "admin/maintenance.html",
            logged_in_user=session.get("username"),
            userid=session.get("userid"),
            page_visibility=page_visibility(),
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load maintenance page: {e}")
        return render_template("handlers/500.html"), 500


@require_permission("admin.maintenance.view")
def api_admin_maintenance_list():
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ID, Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt
            FROM MaintenanceBanner
            ORDER BY StartAt DESC, ID DESC
        """)
        cols = [c[0] for c in cursor.description]
        records = [_maintenance_row_to_dict(row, cols) for row in cursor.fetchall()]
        return jsonify({"success": True, "records": records})
    except Exception as e:
        current_app.logger.error(f"Maintenance list error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_add():
    body = request.get_json(force=True) or {}
    parsed, err = _maintenance_parse_payload(body)
    if err:
        return jsonify({"success": False, "error": err[0]}), err[1]

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO MaintenanceBanner (Title, Message, StartAt, EndAt, Severity, Active, BlockAccess, AnnounceMinutesBefore, CreatedBy, CreatedAt)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
        """,
            [
                parsed["title"],
                parsed["message"],
                parsed["start_at"],
                parsed["end_at"],
                parsed["severity"],
                parsed["active"],
                parsed["block_access"],
                parsed["announce_minutes"],
                session.get("userid"),
            ],
        )
        inserted = cursor.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        new_id = inserted[0]
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True, "id": int(new_id)})
    except Exception as e:
        current_app.logger.error(f"Maintenance add error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_edit(banner_id):
    body = request.get_json(force=True) or {}
    parsed, err = _maintenance_parse_payload(body)
    if err:
        return jsonify({"success": False, "error": err[0]}), err[1]

    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE MaintenanceBanner
               SET Title = ?, Message = ?, StartAt = ?, EndAt = ?, Severity = ?,
                   Active = ?, BlockAccess = ?, AnnounceMinutesBefore = ?
             WHERE ID = ?
        """,
            [
                parsed["title"],
                parsed["message"],
                parsed["start_at"],
                parsed["end_at"],
                parsed["severity"],
                parsed["active"],
                parsed["block_access"],
                parsed["announce_minutes"],
                banner_id,
            ],
        )
        if cursor.rowcount == 0:
            return jsonify({"success": False, "error": "Banner not found"}), 404
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Maintenance edit error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


@require_permission("admin.maintenance.edit")
def api_admin_maintenance_delete(banner_id):
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM MaintenanceBanner WHERE ID = ?", [banner_id])
        if cursor.rowcount == 0:
            return jsonify({"success": False, "error": "Banner not found"}), 404
        conn.commit()
        _MAINTENANCE_BLOCK_CACHE["expires_at"] = 0.0
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Maintenance delete error: {e}")
        return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500
    finally:
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/admin/status", endpoint="admin_status_view", view_func=admin_status_view)

    app.add_url_rule(
        "/api/admin/restart",
        endpoint="api_admin_restart",
        view_func=api_admin_restart,
        methods=["POST"],
    )

    app.add_url_rule(
        "/admin/maintenance", endpoint="admin_maintenance_view", view_func=admin_maintenance_view
    )
    app.add_url_rule(
        "/api/admin/maintenance",
        endpoint="api_admin_maintenance_list",
        view_func=api_admin_maintenance_list,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/admin/maintenance",
        endpoint="api_admin_maintenance_add",
        view_func=api_admin_maintenance_add,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/admin/maintenance/<int:banner_id>",
        endpoint="api_admin_maintenance_edit",
        view_func=api_admin_maintenance_edit,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/admin/maintenance/<int:banner_id>",
        endpoint="api_admin_maintenance_delete",
        view_func=api_admin_maintenance_delete,
        methods=["DELETE"],
    )
