"""External machine-to-machine JSON API, version 1.

One endpoint in v1: GET /api/v1/stats/today -- the dashboard's
imported/processed "today" KPI numbers for the API key's process scope
(dbo.ApiKeys.ProcessList), consumed by an external client's own dashboard.

Auth is per-client API keys (require_api_key in nx_lib/api_auth.py) -- no
session, no CSRF (GET-only; Flask-WTF checks only mutating verbs), and no
i18n: machine-facing English error strings only (do NOT add _() here -- it
would drag in the pybabel cycle). No response cache: the dashboard's
session-keyed cache is meaningless here and one client at 60/min doesn't
need one. PROD serves this under /nexora via PrefixMiddleware:
https://nexora.sydoc.ch/nexora/api/v1/stats/today
"""

from datetime import date

from flask import current_app, g, jsonify

from ..api_auth import require_api_key
from ..extensions import limiter
from .dashboard import compute_today_stats


# NOTE decorator order: @limiter.limit is OUTERMOST -- the deliberate
# OPPOSITE of reporting.py's @require_permission-over-@limiter.limit stack.
# Decorated limits are enforced inside the limit wrapper (flask-limiter
# 3.12), so with auth outermost the 401 paths -- exactly the unauthenticated
# brute-force surface, each a full dbo.ApiKeys scan -- would never be
# throttled. Pinned by test_rate_limit_429_for_unauthenticated_requests.
@limiter.limit("60 per minute")
@require_api_key
def api_v1_stats_today():
    processes = g.api_client["processes"]
    if not processes:
        # Misconfigured key (empty ProcessList): mirror the dashboard's
        # empty-scope zeros rather than erroring -- debuggable from the payload.
        imported_today, processed_today = 0, 0
    else:
        try:
            imported_today, processed_today = compute_today_stats(processes)
        except Exception as e:
            current_app.logger.error(f"external api stats/today failed: {e}")
            return jsonify({"error": "Stats backend unavailable"}), 500
    return jsonify(
        {
            # Server-local calendar date the counts refer to (the SQL uses
            # GETDATE() / CURRENT_DATE -- the same server-local 'today').
            "date": date.today().isoformat(),
            "imported_today": imported_today,
            "exported_today": processed_today,
            "processes": processes,
        }
    )


def register_routes(app):
    app.add_url_rule(
        "/api/v1/stats/today",
        endpoint="api_v1_stats_today",
        view_func=api_v1_stats_today,
    )
