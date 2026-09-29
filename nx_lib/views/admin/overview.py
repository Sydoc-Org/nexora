"""Admin overview: the /admin dashboard."""

import contextlib
import os

from flask import current_app, redirect, render_template, session, url_for

from ... import clients as clients_registry
from ...db import (
    engine_generali_db,
    engine_ms02_docfields_pg,
    engine_ms02_pg,
    engine_ms02_stats_pg,
    engine_nexora_db,
    engine_octo_db,
    engine_statistics_db,
    ping_dbs_parallel,
)
from ...security import page_visibility, require_permission
from .system import _restart_allowed


def _scalar(cursor, sql, params=()):
    """One number, or None when the table is not there yet.

    Every tenancy count below is optional decoration on the overview; a missing
    table on an environment mid-migration must cost that row its meta, not the
    whole page. Rolled back so the failed statement does not poison the rest of
    the batch on the shared cursor.
    """
    try:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        current_app.logger.warning(f"Admin overview count unavailable ({sql.strip()[:60]}): {e}")
        with contextlib.suppress(Exception):
            cursor.connection.rollback()
        return None


def _tenancy_counts(cursor):
    """(tenants, tenants needing attention, organizations not in a tenant).

    "Needs attention" here is the cheap half of what Manage tenants computes:
    a tenant with no organizations at all. The permission-side signal (nobody
    holding ``tenant.<code>.view``) needs the grant join that page already
    does, and is deliberately not duplicated for a link-row meta.
    """
    tenants = _scalar(cursor, "SELECT COUNT(*) FROM dbo.Tenants")
    empty = (
        _scalar(
            cursor,
            "SELECT COUNT(*) FROM dbo.Tenants t WHERE NOT EXISTS ("
            "SELECT 1 FROM organizations o WHERE o.TenantCode = t.TenantCode)",
        )
        or 0
    )
    orphan_orgs = (
        _scalar(cursor, "SELECT COUNT(*) FROM organizations WHERE TenantCode IS NULL") or 0
    )
    return tenants, empty, orphan_orgs


def _client_counts(cursor):
    """(configured connections, how many the runtime did not actually load).

    Same gap the Data Connections page calls out: a row in dbo.Clients says
    "configured", not "running" -- without its env keys _build_clients() skips
    it, so the table and the live registry disagree.
    """
    try:
        cursor.execute("SELECT ClientCode FROM dbo.Clients WHERE IsActive = 1")
        codes = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        current_app.logger.warning(f"dbo.Clients unavailable for the admin overview: {e}")
        with contextlib.suppress(Exception):
            cursor.connection.rollback()
        return None, 0
    return len(codes), sum(1 for code in codes if code not in clients_registry.CLIENTS)


@require_permission("admin.view")
def admin_dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    user_count = 0
    org_count = 0
    active_sessions_count = None
    failed_logins_today = None
    # Tenancy counts for the KPI strip and the link-row metas. Each is its own
    # guarded scalar: on an environment where a tenancy table has not been
    # migrated yet the row simply loses its meta instead of 500-ing the page.
    tenant_count = None
    tenant_attention = 0
    orgs_without_tenant = 0
    user_org_count = None
    client_count = None
    clients_not_loaded = 0
    process_count = None
    status_degraded = 0

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM Users")
        row = cursor.fetchone()
        if row:
            user_count = row[0]

        cursor.execute("SELECT COUNT(*) FROM organizations")
        row = cursor.fetchone()
        if row:
            org_count = row[0]

        cursor.execute("SELECT COUNT(DISTINCT organizationCode) FROM Users")
        row = cursor.fetchone()
        if row:
            user_org_count = row[0]

        cursor.execute("""
            SELECT COUNT(*) FROM ActiveSessions
            WHERE LastSeenAt >= DATEADD(minute, -30, GETDATE())
        """)
        row = cursor.fetchone()
        if row:
            active_sessions_count = row[0]

        # 401 = wrong password or code, 429 = tried while locked out. Not
        # ">= 400": a 400 here is a stale CSRF token (a double-sent 2FA form,
        # a login page left open overnight), and 503 is our own outage --
        # neither is someone getting their credentials wrong.
        # HttpResponseCode is NVARCHAR, so compare as text.
        cursor.execute("""
            SELECT COUNT(*) FROM Logs
            WHERE Path IN ('/login', '/verify_2fa')
              AND HttpRequestMethod = 'POST'
              AND HttpResponseCode IN ('401', '429')
              AND Timestamp >= CAST(GETDATE() AS DATE)
        """)
        row = cursor.fetchone()
        if row:
            failed_logins_today = row[0]

        tenant_count, tenant_attention, orgs_without_tenant = _tenancy_counts(cursor)
        client_count, clients_not_loaded = _client_counts(cursor)
        process_count = _scalar(cursor, "SELECT COUNT(*) FROM dbo.ProcessSources")
        # The Status page reads what ops/outage_monitor.py persisted; this is the
        # same table, reduced to one number, rather than a request-time probe.
        status_degraded = (
            _scalar(
                cursor,
                "SELECT COUNT(*) FROM dbo.StatusComponents WHERE State <> 'operational'",
            )
            or 0
        )
    except Exception as e:
        current_app.logger.error(f"Failed to load admin overview counts: {e}")
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    db_health = ping_dbs_parallel(
        [
            (engine_nexora_db, "Nexora"),
            (engine_octo_db, "Octo"),
            (engine_statistics_db, "Stats"),
            (engine_generali_db, "Generali"),
            *([(engine_ms02_pg, "MS02 (PG)")] if engine_ms02_pg is not None else []),
            *(
                [(engine_ms02_stats_pg, "MS02 stats (PG)")]
                if engine_ms02_stats_pg is not None
                else []
            ),
            *(
                [(engine_ms02_docfields_pg, "MS02 docfields (PG)")]
                if engine_ms02_docfields_pg is not None
                else []
            ),
        ],
        timeout_s=0.8,
    )

    return render_template(
        "admin/admin_overview.html",
        user_count=user_count,
        org_count=org_count,
        user_org_count=user_org_count,
        active_sessions_count=active_sessions_count,
        failed_logins_today=failed_logins_today,
        db_health=db_health,
        tenant_count=tenant_count,
        tenant_attention=tenant_attention,
        orgs_without_tenant=orgs_without_tenant,
        client_count=client_count,
        clients_not_loaded=clients_not_loaded,
        process_count=process_count,
        status_degraded=status_degraded,
        current_env=os.environ.get("ENVIRONMENT", "?"),
        can_restart=_restart_allowed(),
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


def register_routes(app):
    app.add_url_rule("/admin", endpoint="admin_dashboard", view_func=admin_dashboard)
