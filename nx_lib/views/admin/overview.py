"""Admin overview: the /admin dashboard."""

import os

from flask import current_app, redirect, render_template, session, url_for

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


@require_permission("admin.view")
def admin_dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    user_count = 0
    org_count = 0
    active_sessions_count = None
    failed_logins_today = None

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

        cursor.execute("""
            SELECT COUNT(*) FROM ActiveSessions
            WHERE LastSeenAt >= DATEADD(minute, -30, GETDATE())
        """)
        row = cursor.fetchone()
        if row:
            active_sessions_count = row[0]

        cursor.execute("""
            SELECT COUNT(*) FROM Logs
            WHERE Path IN ('/login', '/verify_2fa')
              AND HttpRequestMethod = 'POST'
              AND HttpResponseCode >= 400
              AND Timestamp >= CAST(GETDATE() AS DATE)
        """)
        row = cursor.fetchone()
        if row:
            failed_logins_today = row[0]
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
        active_sessions_count=active_sessions_count,
        failed_logins_today=failed_logins_today,
        db_health=db_health,
        current_env=os.environ.get("ENVIRONMENT", "?"),
        can_restart=_restart_allowed(),
        logged_in_user=session.get("username"),
        userid=session.get("userid"),
        page_visibility=page_visibility(),
    )


def register_routes(app):
    app.add_url_rule("/admin", endpoint="admin_dashboard", view_func=admin_dashboard)
