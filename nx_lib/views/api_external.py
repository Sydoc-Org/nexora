"""External machine-to-machine JSON API, version 1.

Seven endpoints in v1:
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
- GET /api/v1/workitems -- the QUERY endpoint (issue #197): the workitem
  overview page's filters (workitem_id, status, stage, start_date/end_date,
  process, repeated field/value/op/comb doc-field pairs -- incl. invoice
  number) scoped to the key's ProcessList, via the same _get_workitems_data
  path the overview uses (session-less `scope`). Rows carry id, client,
  status, stage, modified_at and import_datetime (Statconfig lookup,
  default client only) -- superseding issue #195's dedicated
  /invoice/import_datetime endpoint, which never shipped.
- GET /api/v1/workitems/fields -- DISCOVERY for the query endpoint: the
  field keys /workitems accepts in ?field= (SearchConfig's col_* columns,
  lowercased with the col_ prefix stripped), sensitive keys excluded. The
  live list, so integrators don't depend on a hand-maintained doc table.
- GET /api/v1/workitems/<id> -- the DETAIL endpoint (issue #197): document
  details (extracted fields + table values) for one workitem, the same data
  the overview row-expand shows (no media/confidence/locations). ?client=
  disambiguates colliding ids. Uniform 404 body for unknown AND
  out-of-scope ids -- no existence oracle.
All consumed by external clients' own integrations.

Sensitive doc-fields (Search_Field_Labels.IsSensitive) are ALWAYS blocked on
this surface -- dbo.ApiKeys has no sensitive grant; if a client ever needs
one, add a column, don't widen the policy here. Unlike the in-app surfaces
(fail-open behind session permissions), a FAILED sensitive-list lookup fails
CLOSED here: get_sensitive_field_keys/tokens return None on error (never
cached) and the workitem endpoints answer 500 instead of serving unstripped
data or accepting unchecked field filters.

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
from werkzeug.datastructures import MultiDict

from ..api_auth import require_api_key
from ..clients import CLIENTS
from ..extensions import limiter
from ..workitem_sources import (
    get_domain_for_workitem,
    get_source_for_workitem,
    process_pair_for_workitem,
    total_backlog_count,
)
from .dashboard import (
    compute_avg_processing_time,
    compute_today_stats,
    compute_undelivered_count,
    format_avg_processing_display,
    resolve_import_datetimes,
)
from .workitems import (
    DOCFIELD_OPS,
    WORKITEM_STAGES,
    _get_workitems_data,
    _load_media_info,
    _norm_field_token,
    get_sensitive_field_keys,
    get_sensitive_field_tokens,
    get_valid_search_columns,
    strip_sensitive_from_detail,
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
        return jsonify({"avg_minutes": None, "avg_display": "—"})
    try:
        # strict=True: same rationale as stats/today -- a stat-row leg
        # failure must surface as a 500, not a false "no data today" null.
        avg_sec = compute_avg_processing_time(processes, strict=True)
    except Exception as e:
        current_app.logger.error(f"external api avg_processing_time failed: {e}")
        return jsonify({"error": "Stats backend unavailable"}), 500
    if avg_sec is None:
        return jsonify({"avg_minutes": None, "avg_display": "—"})
    avg_minutes, avg_display = format_avg_processing_display(avg_sec)
    return jsonify({"avg_minutes": avg_minutes, "avg_display": avg_display})


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


# --------------------------- /api/v1/workitems ----------------------------- #

# The query endpoint's exposed enums (issue #197). Deleted is internal-only
# (workitems.filter.status.deleted) and deliberately not exposed to keys.
WORKITEM_API_STATUSES = ("Ready", "In Progress", "Done")
# Mirrors the overview's perPage whitelist -- validated as strings like ?days=.
WORKITEM_API_PER_PAGE = ("40", "100", "200", "500", "1000")
_DOCFIELD_COMBS = ("and", "or")
# Each doc-field pair fans out into per-SearchConfig-row StatisticsDB
# subqueries; the UI has a practical handful, so bound the machine surface
# too instead of letting one request multiply backend load arbitrarily.
WORKITEM_API_MAX_DOCFIELD_PAIRS = 10


def _parse_workitems_query(processes, *, validate_fields, blocked_keys=frozenset()):
    """Validate the external /workitems query params and translate them into
    the internal MultiDict _get_workitems_data expects. Returns
    (error_message, args); exactly one is None. The API 400s what the
    overview UI silently coerces (unknown enums, bad ops, field-less values)
    -- silent widening is fine UX in-session and an over-return trap on a
    machine surface. validate_fields=False skips the DB-backed doc-field
    whitelist (the /api/test twin must stay zero-backend-query);
    blocked_keys is the caller-resolved sensitive set (the caller has
    already 500'd if that lookup failed -- fail closed, module docstring)."""
    a = request.args
    items = []

    workitem_id = (a.get("workitem_id") or "").strip()
    if workitem_id:
        items.append(("search", workitem_id))

    status = (a.get("status") or "").strip()
    if status:
        if status not in WORKITEM_API_STATUSES:
            return "status must be one of: " + ", ".join(WORKITEM_API_STATUSES), None
        items.append(("status", status))

    stage = (a.get("stage") or "").strip()
    if stage:
        if stage not in WORKITEM_STAGES:
            return "stage must be one of: " + ", ".join(WORKITEM_STAGES), None
        items.append(("stage", stage))

    for param, internal in (("start_date", "startDate"), ("end_date", "endDate")):
        raw = (a.get(param) or "").strip()
        if raw:
            try:
                datetime.fromisoformat(raw)
            except ValueError:
                return (
                    f"{param} must be an ISO datetime (e.g. 2026-08-10 or 2026-08-10T14:30:00)",
                    None,
                )
            items.append((internal, raw))

    process = (a.get("process") or "").strip()
    if process:
        scope = set(processes)
        picked = [p.strip() for p in process.split(",") if p.strip()]
        for p in picked:
            if p not in scope:
                return f"Unknown process '{p}'", None
        items.append(("prcfW", ",".join(picked)))

    fields = a.getlist("field")
    values = a.getlist("value")
    ops = a.getlist("op")
    combs = a.getlist("comb")
    if len(fields) != len(values):
        return "field and value must be supplied in pairs", None
    if len(fields) > WORKITEM_API_MAX_DOCFIELD_PAIRS:
        return f"at most {WORKITEM_API_MAX_DOCFIELD_PAIRS} field/value pairs per request", None
    if len(ops) > len(fields) or len(combs) > len(fields):
        return "more op/comb values than field/value pairs", None
    if validate_fields and fields:
        valid_columns = get_valid_search_columns()
    for i, (f, v) in enumerate(zip(fields, values, strict=True)):
        f = (f or "").strip().lower()
        v = (v or "").strip()
        if not f or not v:
            # No value-first (field-less) search on this surface: an explicit
            # field key is required per pair.
            return "field and value must both be non-empty", None
        if validate_fields and (f"col_{f}" not in valid_columns or f in blocked_keys):
            # Sensitive fields answer identically to unknown ones -- no
            # sensitivity-existence oracle on the external surface.
            return f"Unknown field '{f}'", None
        op = (ops[i] if i < len(ops) else "contains").strip().lower() or "contains"
        if op not in DOCFIELD_OPS:
            return "op must be one of: " + ", ".join(sorted(DOCFIELD_OPS)), None
        comb = (combs[i] if i < len(combs) else "and").strip().lower() or "and"
        if comb not in _DOCFIELD_COMBS:
            return "comb must be 'and' or 'or'", None
        items.extend((("docfield", f), ("docvalue", v), ("docop", op), ("doccomb", comb)))

    page_raw = (a.get("page") or "1").strip()
    if not page_raw.isdigit() or int(page_raw) < 1:
        return "page must be a positive integer", None
    items.append(("page", page_raw))

    per_page = (a.get("per_page") or "40").strip()
    if per_page not in WORKITEM_API_PER_PAGE:
        return "per_page must be one of: " + ", ".join(WORKITEM_API_PER_PAGE), None
    items.append(("perPage", per_page))

    return None, MultiDict(items)


def _api_workitems_scope(processes, blocked_keys):
    """The key's ProcessList as a _get_workitems_data scope -- the session-less
    twin of workitems._session_scope. Sensitive doc-fields are always blocked
    (module docstring; blocked_keys is caller-resolved so a failed lookup has
    already 500'd); the internal-only Deleted status stays hidden."""
    return {
        "allowed": set(processes),
        "can_docfields": True,
        "sensitive_blocked": blocked_keys,
        "can_status": True,
        "can_deleted": False,
        "can_stage": True,
        "can_search_id": True,
        "can_dates": True,
        "persist_selection": False,
        "stamp_register": False,
    }


def _fmt_dt(value):
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def _serialize_workitem_row(row, import_map):
    wid = row["workitemid"]
    # import_datetime only for default-client rows: an MS02 id can collide
    # with a default stat row (compound identity), so a bare-id lookup would
    # stamp another client's date onto it.
    import_dt = import_map.get(str(wid)) if row.get("client") == "default" else None
    return {
        "id": wid,
        "client": row.get("client"),
        "status": row.get("status"),
        "stage": row.get("current_stage"),
        "modified_at": _fmt_dt(row.get("modifiedat")),
        "import_datetime": _fmt_dt(import_dt),
    }


@limiter.limit("60 per minute")
@require_api_key
def api_v1_workitems():
    # Sensitive-list lookup first, and FAIL CLOSED on None (module docstring):
    # with no session-permission fallback on this surface, an unresolved
    # sensitive set must never mean "nothing is sensitive".
    blocked_keys = get_sensitive_field_keys()
    if blocked_keys is None:
        return jsonify({"error": "Workitems backend unavailable"}), 500
    err, args = _parse_workitems_query(
        g.api_client["processes"], validate_fields=True, blocked_keys=blocked_keys
    )
    if err:
        return jsonify({"error": err}), 400
    processes = g.api_client["processes"]
    if not processes:
        # Misconfigured key (empty ProcessList): deterministic empty page,
        # no backend query -- same idiom as stats/today's zeros.
        return jsonify(
            {
                "count": 0,
                "page": 1,
                "per_page": int(args.get("perPage")),
                "total_pages": 0,
                "workitems": [],
            }
        )
    try:
        data = _get_workitems_data(args, scope=_api_workitems_scope(processes, blocked_keys))
        if data["degradedSources"]:
            # Strict contract (stats/today precedent): a dead source must not
            # serve a silently partial page (the UI shows a banner instead).
            raise RuntimeError(f"degraded sources: {data['degradedSources']}")
        default_ids = [r["workitemid"] for r in data["workitems"] if r.get("client") == "default"]
        import_map = resolve_import_datetimes(default_ids, processes, strict=True)
    except Exception as e:
        current_app.logger.error(f"external api workitems query failed: {e}")
        return jsonify({"error": "Workitems backend unavailable"}), 500
    pagination = data["pagination"]
    return jsonify(
        {
            "count": pagination["totalItems"],
            "page": pagination["currentPage"],
            "per_page": pagination["perPage"],
            "total_pages": pagination["totalPages"],
            "workitems": [_serialize_workitem_row(r, import_map) for r in data["workitems"]],
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_v1_workitems_fields():
    # Queryable field keys for /workitems: SearchConfig's col_* columns minus
    # the sensitive set. Fail CLOSED on either lookup failing (module
    # docstring) -- [] from get_valid_search_columns is its error fallback,
    # never a real config state (the table always has col_* columns).
    blocked_keys = get_sensitive_field_keys()
    valid_columns = get_valid_search_columns()
    if blocked_keys is None or not valid_columns:
        return jsonify({"error": "Workitems backend unavailable"}), 500
    fields = sorted(
        key for key in (c.removeprefix("col_") for c in valid_columns) if key not in blocked_keys
    )
    return jsonify({"fields": fields})


def _api_tables(table_sources, blocked_tokens):
    """Reduce the detail panel's table_sources to plain value tables for the
    external API: locations/confidence dropped, and any column whose
    normalized name matches a sensitive doc-field token removed --
    strip_sensitive_from_detail only covers fields/field_sources (no in-app
    surface renders tables to unauthorized callers; the API's fixed
    no-sensitive policy has to cover them itself)."""
    out = []
    for t in table_sources or []:
        cols = [c for c in (t.get("columns") or []) if _norm_field_token(c) not in blocked_tokens]
        rows = [
            [
                {"column": c.get("col"), "value": c.get("value")}
                for c in row
                if _norm_field_token(c.get("col")) not in blocked_tokens
            ]
            for row in (t.get("rows") or [])
        ]
        out.append({"title": t.get("title"), "columns": cols, "rows": rows})
    return out


@limiter.limit("60 per minute")
@require_api_key
def api_v1_workitem_detail(workitem_id):
    client_hint = (request.args.get("client") or "").strip().lower()
    if client_hint and client_hint not in CLIENTS:
        return jsonify({"error": "client must be one of: " + ", ".join(sorted(CLIENTS))}), 400
    processes = g.api_client["processes"]
    if not processes:
        return jsonify({"workitem_id": workitem_id, "detail": None}), 404
    try:
        code = get_source_for_workitem(workitem_id, client_hint=client_hint or None)
        pair = process_pair_for_workitem(workitem_id, client_hint=code)
        key_pairs = {
            (p.split(".")[0].lower(), p.split(".")[-1].lower()) for p in processes if "." in p
        }
        # Uniform 404 body for unresolvable AND out-of-scope ids: the external
        # surface must not be an existence oracle (the session twin
        # _may_view_workitem 403s instead -- deliberate deviation).
        if pair is None or (pair[0].lower(), pair[1].lower()) not in key_pairs:
            return jsonify({"workitem_id": workitem_id, "detail": None}), 404
        domain = get_domain_for_workitem(workitem_id, client_hint=code)
        payload = _load_media_info(workitem_id, domain)
        if payload is None:
            # Unknown document OR runtime backend down -- indistinguishable
            # at this layer (documented); same body as out-of-scope.
            return jsonify({"workitem_id": workitem_id, "detail": None}), 404
        blocked_tokens = get_sensitive_field_tokens()
        if blocked_tokens is None:
            # Fail CLOSED (module docstring): never serve unstripped fields
            # because the sensitive list couldn't be loaded.
            return jsonify({"error": "Workitems backend unavailable"}), 500
        stripped = strip_sensitive_from_detail(payload, blocked_tokens)
        return jsonify(
            {
                "workitem_id": workitem_id,
                "client": code,
                "detail": {
                    "fields": stripped.get("fields", {}),
                    "tables": _api_tables(stripped.get("table_sources"), blocked_tokens),
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"external api workitem detail failed: {e}")
        return jsonify({"error": "Workitems backend unavailable"}), 500


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
    avg_minutes = round(random.uniform(0.5, 120), 1)
    avg_sec = avg_minutes * 60
    _, avg_display = format_avg_processing_display(avg_sec)
    return jsonify({"avg_minutes": avg_minutes, "avg_display": avg_display})


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
def api_test_v1_workitems():
    # Same param validation as the real endpoint MINUS the DB-backed doc-field
    # whitelist (the sandbox stays zero-backend-query -- any field name is
    # accepted here); random rows in the real shape.
    err, args = _parse_workitems_query(g.api_client["processes"], validate_fields=False)
    if err:
        return jsonify({"error": err}), 400
    per_page = int(args.get("perPage"))
    page = args.get("page", 1, type=int)
    count = random.randint(1, 8)
    now = datetime.now()
    rows = []
    for _i in range(count):
        modified = now - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 1439))
        imported = modified - timedelta(hours=random.randint(1, 72))
        rows.append(
            {
                "id": random.randint(1, 99999),
                "client": "default",
                "status": random.choice(WORKITEM_API_STATUSES),
                "stage": random.choice(WORKITEM_STAGES),
                "modified_at": modified.strftime("%Y-%m-%d %H:%M:%S"),
                "import_datetime": imported.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return jsonify(
        {
            "count": count,
            "page": page,
            "per_page": per_page,
            "total_pages": 1,
            "workitems": rows,
        }
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_workitems_fields():
    # Fixed plausible list in the real shape -- the sandbox stays
    # zero-backend-query, so no live SearchConfig read here.
    return jsonify(
        {"fields": ["docdate", "doctype", "grossamount", "invoicenr", "ordernumber", "recipient"]}
    )


@limiter.limit("60 per minute")
@require_api_key
def api_test_v1_workitem_detail(workitem_id):
    # Same ?client= validation as the real endpoint; a plausible fake document
    # (fields + one table) in the real shape, no backend queries.
    client_hint = (request.args.get("client") or "").strip().lower()
    if client_hint and client_hint not in CLIENTS:
        return jsonify({"error": "client must be one of: " + ", ".join(sorted(CLIENTS))}), 400
    fake_nr = f"INV-{date.today().year}-{random.randint(10000, 99999)}"
    return jsonify(
        {
            "workitem_id": workitem_id,
            "client": client_hint or "default",
            "detail": {
                "fields": {
                    "InvoiceNumber": fake_nr,
                    "InvoiceDate": (
                        date.today() - timedelta(days=random.randint(0, 90))
                    ).isoformat(),
                    "TotalAmount": f"{random.uniform(10, 5000):.2f}",
                },
                "tables": [
                    {
                        "title": "LineItems",
                        "columns": ["Description", "Quantity", "Amount"],
                        "rows": [
                            [
                                {"column": "Description", "value": f"Item {i + 1}"},
                                {"column": "Quantity", "value": str(random.randint(1, 9))},
                                {"column": "Amount", "value": f"{random.uniform(5, 500):.2f}"},
                            ]
                            for i in range(random.randint(1, 3))
                        ],
                    }
                ],
            },
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
        "/api/v1/workitems",
        endpoint="api_v1_workitems",
        view_func=api_v1_workitems,
    )
    app.add_url_rule(
        "/api/v1/workitems/fields",
        endpoint="api_v1_workitems_fields",
        view_func=api_v1_workitems_fields,
    )
    app.add_url_rule(
        "/api/v1/workitems/<int:workitem_id>",
        endpoint="api_v1_workitem_detail",
        view_func=api_v1_workitem_detail,
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
        "/api/test/v1/workitems",
        endpoint="api_test_v1_workitems",
        view_func=api_test_v1_workitems,
    )
    app.add_url_rule(
        "/api/test/v1/workitems/fields",
        endpoint="api_test_v1_workitems_fields",
        view_func=api_test_v1_workitems_fields,
    )
    app.add_url_rule(
        "/api/test/v1/workitems/<int:workitem_id>",
        endpoint="api_test_v1_workitem_detail",
        view_func=api_test_v1_workitem_detail,
    )
