"""External machine-to-machine JSON API, version 1.

Three endpoints in v1:
- GET /api/v1/stats/today -- the dashboard's imported/processed "today" KPI
  numbers for the API key's process scope (dbo.ApiKeys.ProcessList).
- GET /api/v1/backlog -- the dashboard's "Current Backlog" KPI number for the
  same process scope. The response deliberately omits the process list --
  scoping happens at key issuance, not in the payload (unlike stats/today,
  kept as-is for compatibility).
- GET /api/v1/undelivered?days=7|10 -- the number of workitems imported in
  the last N days that have no export date yet (issue #196). `days` accepts
  ONLY 7 or 10 (400 otherwise) -- widen the allow-set here and in both docs
  surfaces if a client ever needs another window.
All consumed by an external client's own dashboard.

Each endpoint has a /api/test/v1/... twin (same path suffix, same auth, same
response shape) that returns RANDOM numbers instead of real KPI values -- a
stable sandbox clients can integrate against without touching production
data. Convention (issue #163): every future /api/v1 route gets one of these.

Auth is per-client API keys (require_api_key in nx_lib/api_auth.py) -- no
session, no CSRF (GET-only; Flask-WTF checks only mutating verbs), and no
i18n: machine-facing English error strings only (do NOT add _() here -- it
would drag in the pybabel cycle). No response cache: the dashboard's
session-keyed cache is meaningless here and one client at 60/min doesn't
need one. PROD serves this under /nexora via PrefixMiddleware:
https://nexora.sydoc.ch/nexora/api/v1/stats/today
"""

import random
from datetime import date, datetime

from flask import current_app, g, jsonify, request

from ..api_auth import require_api_key
from ..extensions import limiter
from ..workitem_sources import total_backlog_count
from .dashboard import compute_today_stats, compute_undelivered_count

# The only accepted ?days= values (issue #196) -- validated as strings so no
# int() parsing of raw input is needed.
UNDELIVERED_DAYS = ("7", "10")


def _undelivered_days_or_none():
    """Return the validated ?days= value as an int, or None if absent/invalid."""
    raw = request.args.get("days")
    return int(raw) if raw in UNDELIVERED_DAYS else None


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
            # strict=True: a stat-row leg failure (Statistics DB outage) must
            # RAISE here instead of degrading to zeros like the dashboard --
            # see compute_today_stats' docstring. Without this, an outage
            # produced a 200 of all-zeros indistinguishable from a quiet day.
            imported_today, processed_today = compute_today_stats(processes, strict=True)
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


@limiter.limit("60 per minute")
@require_api_key
def api_v1_backlog():
    processes = g.api_client["processes"]
    if not processes:
        current_backlog = 0
    else:
        try:
            # (client, process) pairs -- see total_backlog_count's docstring
            # for why this must never be split into independent IN-lists.
            pairs = sorted({(p.split(".")[0], p.split(".")[-1]) for p in processes if "." in p})
            current_backlog = total_backlog_count(pairs)
        except Exception as e:
            current_app.logger.error(f"external api backlog failed: {e}")
            return jsonify({"error": "Backlog backend unavailable"}), 500
    return jsonify(
        {
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "current_backlog": current_backlog,
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_v1_undelivered():
    days = _undelivered_days_or_none()
    if days is None:
        return jsonify({"error": "days must be 7 or 10"}), 400
    processes = g.api_client["processes"]
    if not processes:
        undelivered = 0
    else:
        try:
            # strict=True: same rationale as stats/today -- a stat-row leg
            # failure must surface as a 500, not a false "nothing pending" zero.
            undelivered = compute_undelivered_count(processes, days, strict=True)
        except Exception as e:
            current_app.logger.error(f"external api undelivered failed: {e}")
            return jsonify({"error": "Stats backend unavailable"}), 500
    return jsonify(
        {
            "date": date.today().isoformat(),
            "days": days,
            "undelivered": undelivered,
            "processes": processes,
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_stats_today():
    # Real auth (same key a client uses against PROD) but no backend
    # queries -- just plausible random numbers in the real response shape.
    processes = g.api_client["processes"]
    imported_today = random.randint(0, 200)
    return jsonify(
        {
            "date": date.today().isoformat(),
            "imported_today": imported_today,
            "exported_today": random.randint(0, imported_today),
            "processes": processes,
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_backlog():
    return jsonify(
        {
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "current_backlog": random.randint(0, 500),
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_undelivered():
    # Same ?days= validation as the real endpoint so integrations exercise it.
    days = _undelivered_days_or_none()
    if days is None:
        return jsonify({"error": "days must be 7 or 10"}), 400
    return jsonify(
        {
            "date": date.today().isoformat(),
            "days": days,
            "undelivered": random.randint(0, 300),
            "processes": g.api_client["processes"],
        }
    )


def register_routes(app):
    app.add_url_rule(
        "/api/v1/stats/today",
        endpoint="api_v1_stats_today",
        view_func=api_v1_stats_today,
    )
    app.add_url_rule(
        "/api/v1/backlog",
        endpoint="api_v1_backlog",
        view_func=api_v1_backlog,
    )
    app.add_url_rule(
        "/api/v1/undelivered",
        endpoint="api_v1_undelivered",
        view_func=api_v1_undelivered,
    )
    app.add_url_rule(
        "/api/test/v1/stats/today",
        endpoint="api_test_v1_stats_today",
        view_func=api_test_v1_stats_today,
    )
    app.add_url_rule(
        "/api/test/v1/backlog",
        endpoint="api_test_v1_backlog",
        view_func=api_test_v1_backlog,
    )
    app.add_url_rule(
        "/api/test/v1/undelivered",
        endpoint="api_test_v1_undelivered",
        view_func=api_test_v1_undelivered,
    )
