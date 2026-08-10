"""External machine-to-machine JSON API, version 1.

Five endpoints in v1:
- GET /api/v1/stats/today -- the dashboard's imported/processed "today" KPI
  numbers for the API key's process scope (dbo.ApiKeys.ProcessList).
- GET /api/v1/backlog -- the dashboard's "Current Backlog" KPI number for the
  same process scope. The response deliberately omits the process list --
  scoping happens at key issuance, not in the payload (unlike stats/today,
  kept as-is for compatibility).
- GET /api/v1/avg_processing_time -- the dashboard's "Avg Processing
  Time" KPI number for the API key's process scope. See
  compute_avg_processing_time's docstring (nx_lib/views/dashboard.py) for the
  exact calculation (mean of per-source AVG(export - import) seconds among
  rows exported today, NOT weighted by row count).
- GET /api/v1/undelivered?days=7|10 -- the number of workitems imported in
  the last N days that have no export date yet (issue #196). `days` accepts
  ONLY 7 or 10 (400 otherwise) -- widen the allow-set here and in both docs
  surfaces if a client ever needs another window. Like /backlog, the
  response omits the process list.
- GET /api/v1/invoice/import_datetime?invoice_nr=<nr> -- the import datetime
  for a single invoice number (issue #195), resolved via
  resolve_invoice_import_datetime (nx_lib/views/dashboard.py). Default client
  only (SearchConfig.col_invoicenr); scoped to the key's ProcessList same as
  the other two. 404 if invoice_nr is unmapped/not found among the key's
  processes.
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
from datetime import date, datetime, timedelta

from flask import current_app, g, jsonify, request

from ..api_auth import require_api_key
from ..extensions import limiter
from ..workitem_sources import total_backlog_count
from .dashboard import (
    compute_avg_processing_time,
    compute_today_stats,
    compute_undelivered_count,
    format_avg_processing_display,
    resolve_invoice_import_datetime,
)

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
def api_v1_avg_processing_time():
    processes = g.api_client["processes"]
    if not processes:
        return jsonify({"avg_minutes": None, "avg_display": "—", "processes": processes})
    try:
        # strict=True: same rationale as stats/today -- a stat-row leg
        # failure must surface as a 500, not a false "no data today" null.
        avg_sec = compute_avg_processing_time(processes, strict=True)
    except Exception as e:
        current_app.logger.error(f"external api avg_processing_time failed: {e}")
        return jsonify({"error": "Stats backend unavailable"}), 500
    if avg_sec is None:
        return jsonify({"avg_minutes": None, "avg_display": "—", "processes": processes})
    avg_minutes, avg_display = format_avg_processing_display(avg_sec)
    return jsonify({"avg_minutes": avg_minutes, "avg_display": avg_display, "processes": processes})


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
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_v1_invoice_import_datetime():
    invoice_nr = (request.args.get("invoice_nr") or "").strip()
    if not invoice_nr:
        return jsonify({"error": "Missing required query param 'invoice_nr'"}), 400
    processes = g.api_client["processes"]
    if not processes:
        return jsonify({"invoice_nr": invoice_nr, "import_datetime": None}), 404
    try:
        # strict=True: same rationale as stats/today -- a StatisticsDB
        # failure must surface as a 500, not a false "not found".
        import_dt, _process = resolve_invoice_import_datetime(invoice_nr, processes, strict=True)
    except Exception as e:
        current_app.logger.error(f"external api invoice import_datetime failed: {e}")
        return jsonify({"error": "Stats backend unavailable"}), 500
    if import_dt is None:
        return jsonify({"invoice_nr": invoice_nr, "import_datetime": None}), 404
    return jsonify(
        {
            "invoice_nr": invoice_nr,
            "import_datetime": import_dt.strftime("%Y-%m-%d %H:%M:%S"),
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
def api_test_v1_avg_processing_time():
    processes = g.api_client["processes"]
    avg_minutes = round(random.uniform(0.5, 120), 1)
    avg_sec = avg_minutes * 60
    _, avg_display = format_avg_processing_display(avg_sec)
    return jsonify({"avg_minutes": avg_minutes, "avg_display": avg_display, "processes": processes})


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
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_invoice_import_datetime():
    # Real auth, no backend query -- a plausible random datetime in the last
    # 90 days, in the real response shape.
    invoice_nr = (request.args.get("invoice_nr") or "").strip()
    if not invoice_nr:
        return jsonify({"error": "Missing required query param 'invoice_nr'"}), 400
    fake_dt = datetime.now() - timedelta(
        days=random.randint(0, 90), hours=random.randint(0, 23), minutes=random.randint(0, 59)
    )
    return jsonify(
        {
            "invoice_nr": invoice_nr,
            "import_datetime": fake_dt.strftime("%Y-%m-%d %H:%M:%S"),
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
        "/api/v1/avg_processing_time",
        endpoint="api_v1_avg_processing_time",
        view_func=api_v1_avg_processing_time,
    )
    app.add_url_rule(
        "/api/v1/undelivered",
        endpoint="api_v1_undelivered",
        view_func=api_v1_undelivered,
    )
    app.add_url_rule(
        "/api/v1/invoice/import_datetime",
        endpoint="api_v1_invoice_import_datetime",
        view_func=api_v1_invoice_import_datetime,
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
        "/api/test/v1/avg_processing_time",
        endpoint="api_test_v1_avg_processing_time",
        view_func=api_test_v1_avg_processing_time,
    )
    app.add_url_rule(
        "/api/test/v1/undelivered",
        endpoint="api_test_v1_undelivered",
        view_func=api_test_v1_undelivered,
    )
    app.add_url_rule(
        "/api/test/v1/invoice/import_datetime",
        endpoint="api_test_v1_invoice_import_datetime",
        view_func=api_test_v1_invoice_import_datetime,
    )
