"""Workitems: list, detail, media, audit, comments, tags, priority, assignment,
plus the CSV exporter."""

import base64
import concurrent.futures
import csv
import io
import json
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pyodbc
import requests
from flask import (
    Response,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_babel import gettext as _
from PIL import Image
from werkzeug.utils import secure_filename

from .. import mapping_config
from ..clients import CLIENTS
from ..config import DB_STATISTICS, OCTO_DOMAIN, PATHS
from ..db import engine_ms02_docfields_pg, engine_nexora_db, engine_statistics_db
from ..extensions import cache
from ..files import is_file_allowed
from ..i18n import get_locale
from ..octo import (
    get_access_token,
    get_activity_type_name,
    get_extensions_urls_fields,
    get_media,
    get_workitemdata_param,
    pdf_src_bytes,
    render_pdf_page_jpeg,
)
from ..prepared_documents import (
    GROUP_BY_COLUMNS,
    clear_prepared_documents,
    count_prepared_documents,
    fetch_prepared_documents_page,
    pids_in_register,
    upsert_prepared_documents,
)
from ..process_helpers import (
    get_activity_instances_to_ignore,
    normalize_process_selection,
    prepare_process_selection_lists,
)
from ..security import (
    PermissionDenied,
    has_permission,
    page_visibility,
    require_permission,
)
from ..workitem_sources import (
    _MS02_IDENT,
    _resolve_octo_wid_stage_pg,
    fetch_merged_page,
    get_domain_for_workitem,
    parse_prepared_xlsx,
    process_pair_for_workitem,
    resolve_ms02_docfield_ids,
    resolve_ms02_pid_to_wids,
    resolve_ms02_wids_to_pids,
    resolve_octo_wid_stage,
)
from ..workitems import fields as _wi_fields
from ..workitems import query as _query
from ..workitems.fields import (
    DOCFIELD_OPS,  # noqa: F401 -- re-exported for api_external.py
    _build_field_config,
    _docfield_ids_cache_key,  # noqa: F401 -- re-exported for tests
    _docfield_pairs_normalized,  # noqa: F401 -- re-exported for tests
    _docfield_predicate,  # noqa: F401 -- re-exported for tests
)
from ..workitems.media import load_media_info as _load_media_info_core
from ..workitems.media import wi_cache_key as _wi_cache_key
from ..workitems.query import ms02_pid_specs as _ms02_pid_specs
from ..workitems.query import ms02_prepared_docs_processes as _ms02_prepared_docs_processes
from ..workitems.sensitivity import (
    _norm_field_token,  # noqa: F401 -- re-exported for tests
    drop_sensitive_options,
    get_search_columns_for_processes,  # noqa: F401 -- re-exported for api_external.py
    get_sensitive_field_keys,
    get_sensitive_field_tokens,
    get_valid_search_columns,
    strip_export_fields,
    strip_sensitive_fields,  # noqa: F401 -- re-exported for tests
    strip_sensitive_from_detail,
)

# ---------------------------- field/config helpers ---------------------------- #


def api_config_fields():
    if "username" not in session:
        return jsonify({}), 401

    perms = session.get("permissions", [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split(".")[-2] + "." + perm.split(".")[-1])
        for perm in perms
        if perm.startswith(prefix)
    }

    current_lang = str(get_locale())
    _sees_sensitive = has_permission("workitems.filter.documentfields.sensitive")
    _cache_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}_s{int(_sees_sensitive)}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    search_options, db_labels_map = _build_field_config(allowed_processes, current_lang)

    blocked = sensitive_blocked_keys()
    if blocked:
        search_options = drop_sensitive_options(search_options, blocked)
        db_labels_map = {k: v for k, v in db_labels_map.items() if k.lower() not in blocked}
    result = {"search_options": search_options, "labels": db_labels_map}
    cache.set(_cache_key, result, timeout=3600)
    return jsonify(result)


# DOCFIELD_OPS, _docfield_predicate, _docfield_pairs_normalized and
# _docfield_ids_cache_key moved to nx_lib/workitems/fields.py (pure doc-value
# search DSL, #98/#148) and are imported above. _docfield_op/_docfield_comb
# stay reachable here as thin module-qualified forwarders so a caller/test
# that wants to intercept a call made from inside nx_lib.workitems.query (the
# only other caller) patches nx_lib.workitems.fields directly instead.
def _docfield_op(docops, i):
    return _wi_fields._docfield_op(docops, i)


def _docfield_comb(doccombs, i):
    return _wi_fields._docfield_comb(doccombs, i)


# get_valid_search_columns/get_search_columns_for_processes/_norm_field_token/
# strip_sensitive_fields/drop_sensitive_options/get_sensitive_field_keys/
# get_sensitive_field_tokens/strip_sensitive_from_detail moved to
# nx_lib/workitems/sensitivity.py (#98 phase 2, pure Python -- no Flask) and
# are imported above (still reachable/patchable as module attributes here,
# e.g. wv.get_sensitive_field_keys). sensitive_blocked_keys/tokens keep the
# same 0-arg signature and body here -- has_permission(...) reads session, so
# the read stays Flask-aware in this file; nx_lib.workitems.sensitivity carries
# the equivalent pure core (sensitive_blocked_keys(has_sensitive_perm)/
# sensitive_blocked_tokens(has_sensitive_perm)) for Flask-free callers, taking
# the already-resolved boolean explicitly per D4.
def sensitive_blocked_keys():
    """FieldKeys the CURRENT user may not use (empty if they hold the perm).
    Coerces a failed lookup (None) to set() -- in-app fail-open, unchanged."""
    if has_permission("workitems.filter.documentfields.sensitive"):
        return set()
    return get_sensitive_field_keys() or set()


def sensitive_blocked_tokens():
    """Octo name-tokens the CURRENT user may not see (empty if they hold perm).
    Coerces a failed lookup (None) to set() -- in-app fail-open, unchanged."""
    if has_permission("workitems.filter.documentfields.sensitive"):
        return set()
    return get_sensitive_field_tokens() or set()


def _strip_export_fields(details_map, blocked_tokens):
    """In-place: drop sensitive field entries from every detail's fields dict
    before CSV headers/rows are built. No-op when blocked_tokens is empty."""
    strip_export_fields(details_map, blocked_tokens)


def _ms02_target_processes():
    """The user's MS02-eligible process allow-list, derived the same way
    _get_workitems_data does (from workitems.filter.process.* perms)."""
    prefix = "workitems.filter.process."
    out = []
    for perm in session.get("permissions", []):
        if perm.startswith(prefix):
            parts = perm.split(".")
            if len(parts) >= 2:
                out.append(f"{parts[-2]}.{parts[-1]}")
    return out


# _ms02_pid_specs/_ms02_prepared_docs_processes moved to
# nx_lib/workitems/query.py (pure -- no session, just mapping_config) and are
# imported above under their original names.


# Hard ceiling on a CSV export. It used to be 5000 with no signal to the user,
# which silently dropped ~34k of PROD's ~39k visible workitems from a full
# export. Truncation is now both far less likely and explicitly reported (see
# export_workitems_csv).
# ponytail: single in-memory page, not a streaming cursor — revisit if exports
# outgrow this ceiling.
EXPORT_MAX_ROWS = 100_000

# Fixed domain of the derived stage CASE both source adapters compute -- see
# workitem_sources.py's WorkitemCTE/ranked CurrentStage column and the
# timeline stepper in _workitem_detail_panel_js.html (`stages` array).
WORKITEM_STAGES = ("Import", "Extraction", "Validation", "Delivery")

# D-CSVLIM: include=fields|history|images are all per-row Octo fetches. The
# UI only ever offers them once <=10 rows are selected (see
# selectedIds.size <= 10 in _workitems_overview_js.html), but that gate is
# client-side only -- a direct API call could request a heavy include with no
# `ids` (or an arbitrarily large one) and walk up to EXPORT_MAX_ROWS rows
# doing per-row Octo fetches. Enforced server-side in export_workitems_csv.
EXPORT_HEAVY_INCLUDE_MAX_IDS = 10

# Per-row Octo fetches (fields/history/images) run on a bounded thread pool
# with an overall as_completed() wait budget (see export_workitems_csv). If
# that budget is exhausted while rows are still pending, those rows get this
# marker in place of whatever include= columns they would have carried,
# rather than either silently showing blank data or 500ing the whole export.
EXPORT_TIMEOUT_MARKER = "(export timed out)"


def _client_hint():
    """Client code the front-end row carried (``?client=ms02``), or None.

    Workitem ids are not unique across clients, so the row the user clicked is
    the only reliable disambiguator; unknown/absent values fall through to the
    probe path in ``get_source_for_workitem``."""
    hint = (request.args.get("client") or "").strip().lower()
    return hint if hint in CLIENTS else None


def _granted_process_pairs():
    """(client, process) pairs the caller holds a workitems grant for, lowered
    for case-insensitive comparison (the list query authorizes these via a
    case-insensitive SQL `=`, so the entitlement check must match that)."""
    pairs = prepare_process_selection_lists("workitems.filter.process.", "all")
    return {(c.lower(), p.lower()) for c, p in pairs}


def _may_view_workitem(workitem_id):
    """Whether the caller is entitled to this workitem's (client, process).

    Closes the cross-tenant / cross-process detail IDOR (#193): the by-id
    detail endpoints resolved the tenant from a caller-supplied ?client= and
    fetched an arbitrary id behind only a flat details.view* code, never an
    ownership check. Fails closed when the pair can't be resolved."""
    pair = process_pair_for_workitem(workitem_id, client_hint=_client_hint())
    if pair is None:
        return False
    return (pair[0].lower(), pair[1].lower()) in _granted_process_pairs()


def _stamp_in_register(rows):
    """MS02-only, in place: stamp row['pid'] + row['in_register'] onto each visible
    workitem row. Resolves the page's wids -> PIDs (resolve_ms02_wids_to_pids) and
    intersects with the register (pids_in_register). Guarded so the default client /
    CI path is byte-for-byte unchanged; never raises into the request."""
    ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
    if not (ms02_active and rows):
        return
    # The PID is a personal identifying number: honour the same sensitive
    # doc-field gate every other surface applies, instead of stamping it onto
    # every list row unconditionally.
    if "pid" in sensitive_blocked_keys():
        return
    # Only MS02 rows may be resolved against the MS02 PID table. Ids collide
    # across clients, so a default-client row with the same number would
    # otherwise be stamped with an unrelated MS02 person's PID.
    ms02_rows = [r for r in rows if r.get("client") == "ms02"]
    if not ms02_rows:
        return
    try:
        pid_specs = _ms02_pid_specs(_ms02_target_processes())
        wid_to_pid = (
            resolve_ms02_wids_to_pids(
                engine_ms02_docfields_pg, pid_specs, [r["workitemid"] for r in ms02_rows]
            )
            if pid_specs
            else None
        ) or {}
        registered = pids_in_register(list(wid_to_pid.values())) if wid_to_pid else set()
        for r in ms02_rows:
            pid = wid_to_pid.get(r["workitemid"])
            r["pid"] = pid or ""
            r["in_register"] = bool(pid and pid in registered)
    except Exception as e:
        current_app.logger.error(f"_stamp_in_register: {e}")


def _session_scope():
    """The interactive callers' filter scope for _get_workitems_data: every
    session/permission read the list path needs, gathered in one place so the
    query body itself stays session-free. The external API builds its own
    scope from the key's ProcessList instead (nx_lib/views/api_external.py) --
    same keys, no session."""
    prefix = "workitems.filter.process."
    perms = session.get("permissions", [])
    allowed = set()
    for perm in perms:
        if perm.startswith(prefix):
            parts = perm.split(".")
            if len(parts) >= 2:
                allowed.add(f"{parts[-2]}.{parts[-1]}")
    return {
        # compound '<client>.<process>' strings the caller may see
        "allowed": allowed,
        "can_docfields": has_permission("workitems.filter.documentfields"),
        "sensitive_blocked": sensitive_blocked_keys(),
        "can_status": has_permission("workitems.filter.status"),
        "can_deleted": has_permission("workitems.filter.status.deleted"),
        "can_stage": has_permission("workitems.filter.stage"),
        "can_search_id": has_permission("workitems.filter.workitemid"),
        "can_dates": has_permission("workitems.filter.datetime"),
        # remember the process selection in the session (overview UI state)
        "persist_selection": True,
        # stamp MS02 pid/in_register onto rows (reads session twice internally)
        "stamp_register": True,
    }


# The 395-line query engine (doc-field pre-resolution + WorkitemFilter
# construction + fetch_merged_page) now lives in nx_lib.workitems.query,
# Flask-free (D4). This wrapper keeps the historical signature/return shape
# and does the two things that stay inherently Flask-aware:
#   - reads this module's OWN globals (engines, resolvers, cache, DOCFIELD_OPS
#     helpers via get_valid_search_columns()) so every existing monkeypatch-
#     based test (which patches those names on nx_lib.views.workitems)
#     keeps working unchanged;
#   - persists the resolved process-selection to session and stamps MS02
#     pid/in_register rows (both real session/current_app touches).
def _get_workitems_data(args, export_all=False, scope=None):
    if scope is None:
        scope = _session_scope()
    result = _query.get_workitems_data(
        args,
        scope,
        export_all=export_all,
        valid_db_columns_fn=get_valid_search_columns,
        activity_ignore_map=get_activity_instances_to_ignore(),
        engine_statistics_db=engine_statistics_db,
        engine_ms02_docfields_pg=engine_ms02_docfields_pg,
        resolve_ms02_docfield_ids=resolve_ms02_docfield_ids,
        fetch_merged_page=fetch_merged_page,
        cache=cache,
        logger=current_app.logger,
        export_max_rows=EXPORT_MAX_ROWS,
        workitem_stages=WORKITEM_STAGES,
    )
    process_name = result.pop("process_name")
    if scope["persist_selection"]:
        session["process_name_workitemOverview"] = process_name
    if scope["stamp_register"]:
        _stamp_in_register(result["workitems"])
    return result


# nx_lib.workitems.query.docfield_suggestions_any_field is the Flask-free
# core (D4). This wrapper keeps the historical signature/JSON-response shape
# and reads engines/cache off this module's OWN globals so the existing
# monkeypatch-based tests (which patch those names on nx_lib.views.workitems)
# keep working unchanged.
def _docfield_values_all_fields(target_processes, q):
    """Value-first mode of /api/docfield_values (issue #148): no field picked ->
    labeled suggestions ``[{value, field}]`` across every permitted,
    non-sensitive field, so the UI can show which field a value lives in and
    lock the pair on pick. The field-specific path keeps its flat string list."""
    blocked = sensitive_blocked_keys()
    target_cols = [c for c in get_valid_search_columns() if c not in blocked]
    try:
        pairs = _query.docfield_suggestions_any_field(
            target_processes,
            target_cols,
            engine_statistics_db=engine_statistics_db,
            engine_ms02_docfields_pg=engine_ms02_docfields_pg,
            cache=cache,
            logger=current_app.logger,
        )
    except Exception as e:
        current_app.logger.error(f"/api/docfield_values any-field error: {e}")
        return jsonify({"error": _("Could not fetch values")}), 500

    q_lower = q.lower()
    return jsonify(
        [{"value": v, "field": f} for v, f in pairs if not q or q_lower in v.lower()][:15]
    )


# ---------------------------- routes ---------------------------- #


@require_permission("workitems.filter.documentfields")
def api_docfield_values():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    process = request.args.get("process", "all")
    field = (request.args.get("field", "") or "").lower().strip()
    q = (request.args.get("q", "") or "").strip()

    # Whitelist `field` against the known registry field keys before it drives
    # any mapping_config lookup or cache key below (the same guard the
    # workitems search path uses) -- it is a raw request arg. No field at all
    # = value-first mode, handled after the process gating.
    if field:
        if field not in get_valid_search_columns():
            return jsonify([])
        if field in sensitive_blocked_keys():
            return jsonify([])

    # Fail-closed process gating: `process` is a caller-supplied arg and must
    # not be trusted as-is -- a caller holding only the blanket
    # workitems.filter.documentfields perm could otherwise pull value
    # suggestions from any process, including ones they hold no
    # workitems.filter.process.<p> grant for. Reuse _ms02_target_processes(),
    # the existing workitems.filter.process.* allow-list helper, rather than
    # re-deriving it; "all" narrows to the caller's own allowed set rather
    # than every process configured in the mapping_config registry.
    allowed_processes_set = set(_ms02_target_processes())

    # `process` is "all" or a comma-joined multi-selection (issue #150);
    # unknown/ungranted entries are dropped by normalize_process_selection.
    target_processes = normalize_process_selection(process, allowed_processes_set)[1]

    if not target_processes:
        return jsonify([])

    if not field:
        return _docfield_values_all_fields(target_processes, q)

    try:
        # MS02 processes resolve suggestions from the separate doc-field DB, not
        # [DB_STATISTICS]: a 'ms02' ProcessFieldMappings row carries the wide
        # statistik-table COLUMN name for this field. Mirrors the two-leg
        # default/ms02 split the workitems search resolution uses above --
        # when this field is mapped for ms02 on ANY targeted process, ms02 is
        # the sole source of suggestions for it (matches the legacy behaviour).
        ms02_sources = {s.process: s for s in mapping_config.sources_for("ms02", target_processes)}
        ms02_configs = []  # (table, column, suggestion_time_filter)
        for m in mapping_config.mappings_for("ms02", target_processes, field_keys={field}):
            src = ms02_sources.get(m.process)
            if src is None or not src.table or not m.column:
                continue
            ms02_configs.append((src.table, m.column, src.suggestion_time_filter))

        if ms02_configs:
            if engine_ms02_docfields_pg is None:
                return jsonify([])
            ms02_cache_key = f"docfield_vals_ms02_{'_'.join(sorted(target_processes))}_{field}"
            all_vals = cache.get(ms02_cache_key)
            if all_vals is None:
                df_conn = None
                raw_vals = []
                try:
                    df_conn = engine_ms02_docfields_pg.raw_connection()
                    df_cur = df_conn.cursor()
                    for table, col, stf in ms02_configs:
                        if not _MS02_IDENT.match(col):  # defense-in-depth on the column
                            continue
                        sql = (
                            f'SELECT DISTINCT "{col}"::text AS v FROM {table} '
                            f'WHERE "{col}"::text IS NOT NULL AND "{col}"::text <> %s'
                        )
                        if stf:
                            sql += f" AND {stf}"
                        sql += " ORDER BY v LIMIT 500"
                        df_cur.execute(sql, [""])
                        raw_vals.extend(r[0] for r in df_cur.fetchall())
                    df_cur.close()
                except Exception as e:
                    current_app.logger.error(f"/api/docfield_values ms02 error: {e}")
                    raw_vals = []
                finally:
                    if df_conn:
                        df_conn.close()
                all_vals = sorted(set(raw_vals))
                cache.set(ms02_cache_key, all_vals, timeout=600)
            q_lower = q.lower()
            return jsonify([v for v in all_vals if not q or q_lower in v.lower()][:15])

        cache_key = f"docfield_vals_{'_'.join(sorted(target_processes))}_{field}"
        all_vals = cache.get(cache_key)

        if all_vals is None:
            default_sources = {
                s.process: s for s in mapping_config.sources_for("default", target_processes)
            }
            parts = []
            for m in mapping_config.mappings_for("default", target_processes, field_keys={field}):
                src = default_sources.get(m.process)
                if src is None or not src.table or not m.column:
                    continue
                safe_col = f"CAST({m.column} AS NVARCHAR(MAX))"
                parts.append(f"""
                    SELECT {safe_col} COLLATE DATABASE_DEFAULT AS Val
                    FROM [{DB_STATISTICS}].{src.table}
                    WHERE {m.column} IS NOT NULL
                      AND {safe_col} <> ''
                      AND {src.suggestion_time_filter}
                """)

            raw_vals = []
            if parts:
                stat_conn = None
                try:
                    full_union_sql = " UNION ALL ".join(parts)
                    final_sql = f"""
                        SELECT DISTINCT TOP 500 Val
                        FROM ({full_union_sql}) t
                        ORDER BY Val
                    """
                    stat_conn = engine_statistics_db.raw_connection()
                    stat_cur = stat_conn.cursor()
                    stat_cur.execute(final_sql)
                    raw_vals.extend(row.Val for row in stat_cur.fetchall())
                    stat_cur.close()
                finally:
                    if stat_conn:
                        stat_conn.close()

            all_vals = sorted(set(raw_vals))
            cache.set(cache_key, all_vals, timeout=600)

        q_lower = q.lower()
        results = [v for v in all_vals if not q or q_lower in v.lower()][:15]
        return jsonify(results)

    except Exception as e:
        current_app.logger.error(f"/api/docfield_values error: {e}")
        return jsonify({"error": _("Could not fetch values")}), 500


@require_permission("workitems.view")
def api_workitems():
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401
    try:
        data = _get_workitems_data(request.args)
        return jsonify(data)
    except Exception as e:
        current_app.logger.error(f"API error in workitems overview: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


@require_permission("workitems.view")
def export_workitems_csv():
    """Export workitems as CSV. Supports optional doc fields, audit history, and images."""
    if "username" not in session:
        return jsonify({"error": "Not authorized"}), 401

    include_set = set(request.args.get("include", "").split(","))
    include_fields = "fields" in include_set and has_permission("workitems.details.view.fields")
    include_history = "history" in include_set and has_permission("workitems.details.view.audit")
    include_images = "images" in include_set and has_permission("workitems.details.view.images")

    # Selective export ("export selected checked rows") comes in as compound
    # `client-id` pairs, matching the `rowKey` the workitems list already
    # builds per row (_workitems_overview_js.html renderTable/checkbox
    # data-id). Workitem ids are NOT globally unique across clients (1216
    # collides between the default Octo client and MS02, see
    # docs/design/ms02-multisource.md) -- filtering on the bare id let
    # selecting one client's row also export the other client's row sharing
    # that id. The UI is the only caller of this param and always sends the
    # compound form now, so bare-id values are simply ignored rather than
    # silently matching any client.
    ids_param = request.args.get("ids", "").strip()
    specific_ids = set()
    if ids_param:
        for part in ids_param.split(","):
            part = part.strip()
            client_part, sep, wid_part = part.rpartition("-")
            if sep and client_part and wid_part.isdigit():
                specific_ids.add((client_part, int(wid_part)))

    # D-CSVLIM: server-side enforcement of the heavy-include selection cap
    # (see EXPORT_HEAVY_INCLUDE_MAX_IDS above) -- an include= request must
    # name a selection of at most that many compound ids, never an absent or
    # oversized one.
    if (include_set & {"fields", "history", "images"}) and (
        not specific_ids or len(specific_ids) > EXPORT_HEAVY_INCLUDE_MAX_IDS
    ):
        return (
            jsonify(
                {
                    "error": _(
                        "Exporting fields, history, or images requires selecting "
                        "10 or fewer workitems."
                    )
                }
            ),
            400,
        )

    try:
        result = _get_workitems_data(request.args, export_all=True)
        workitems = result.get("workitems", [])
        matched_total = result.get("pagination", {}).get("totalItems", len(workitems))
    except Exception as e:
        current_app.logger.error(f"Export: failed to fetch workitems: {e}")
        return jsonify({"error": "Failed to fetch workitems"}), 500

    truncated = matched_total > len(workitems)
    if truncated:
        current_app.logger.warning(
            f"Export truncated: {len(workitems)} of {matched_total} matching workitems "
            f"(cap {EXPORT_MAX_ROWS}); user={session.get('username')}"
        )

    if specific_ids:
        workitems = [w for w in workitems if (w.get("client"), w["workitemid"]) in specific_ids]

    if not workitems:
        output = io.StringIO()
        output.write("No workitems to export\r\n")
        resp = make_response(output.getvalue())
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = "attachment; filename=workitems_export.csv"
        return resp

    # Workitem ids are NOT globally unique across clients (1216 collides
    # between the default Octo client and MS02) -- domains/details/caches
    # below are all keyed by (client, wid), and the client hint the row
    # already carries is forwarded to get_domain_for_workitem rather than
    # re-probed, per D9. A bare-id key here would let the second row of a
    # colliding id silently answer for (or overwrite the cached entry of)
    # the first.
    domains = {}
    for w in workitems:
        wid = w["workitemid"]
        client = w.get("client")
        try:
            domains[(client, wid)] = get_domain_for_workitem(wid, client_hint=client)
        except Exception:
            domains[(client, wid)] = OCTO_DOMAIN

    _include_fields = include_fields
    _include_history = include_history
    _include_images = include_images
    _app = current_app._get_current_object()

    def _fetch(wid, client):
        detail = {"fields": {}, "history": [], "images": []}
        domain = domains.get((client, wid), OCTO_DOMAIN)
        with _app.app_context():
            if _include_fields or _include_images:
                try:
                    urls, extensions = [], []
                    # Read-through only: this path never fetches with
                    # with_tables=True (see get_extensions_urls_fields), so its
                    # payload lacks field_sources/table_sources. Writing that
                    # reduced shape under the media_info key would poison the
                    # next api_get_media_info request for this workitem --
                    # the source-highlight overlay would go silently empty. A
                    # cache hit (populated by the detail panel) still short-
                    # circuits the Octo call; a miss is simply not cached here.
                    cached = cache.get(_wi_cache_key("media_info", wid, domain))
                    if cached:
                        detail["fields"] = cached.get("fields", {})
                    else:
                        returndata = get_workitemdata_param(wid, domain)
                        if returndata:
                            workitemdata, document_id = returndata
                            extensions, urls, fields, _fs, _ts = get_extensions_urls_fields(
                                workitemdata, document_id, domain
                            )
                            detail["fields"] = fields
                            if urls:
                                cache.set(
                                    _wi_cache_key("media_data", wid, domain),
                                    {"extensions": extensions, "urls": urls},
                                )
                    if _include_images:
                        cached_media = cache.get(_wi_cache_key("media_data", wid, domain))
                        if cached_media:
                            urls = cached_media.get("urls", [])
                            extensions = cached_media.get("extensions", [])
                        for i, (img_url, ext) in enumerate(
                            zip(urls[:5], extensions[:5], strict=False)
                        ):
                            try:
                                img_bytes = get_media(img_url, domain)
                                if str(ext).lower() in (".tif", ".tiff"):
                                    with Image.open(io.BytesIO(img_bytes)) as img:
                                        if img.mode != "RGB":
                                            img = img.convert("RGB")
                                        buf = io.BytesIO()
                                        img.save(buf, "JPEG", quality=75)
                                        img_bytes = buf.getvalue()
                                detail["images"].append(base64.b64encode(img_bytes).decode("utf-8"))
                            except Exception as img_err:
                                _app.logger.warning(
                                    f"Export: image {i} for {wid} failed: {img_err}"
                                )
                except Exception as e:
                    _app.logger.error(f"Export: doc fields error for {wid}: {e}")

            if _include_history:
                try:
                    cached = cache.get(_wi_cache_key("audithistory", wid, domain))
                    if cached is not None:
                        detail["history"] = cached
                    else:
                        audit_url = (
                            f"https://{domain}/api/processservice/api/v2.1/processService/"
                            f"WorkItemAudits?WorkItemID={wid}&VerifyAuditSignatures=true"
                        )
                        token = get_access_token(domain)
                        resp = requests.get(
                            audit_url, headers={"Authorization": f"Bearer {token}"}, timeout=15
                        )
                        resp.raise_for_status()
                        audits_data = resp.json()
                        unique_acts = {}
                        for audit in (
                            audits_data.get("Audits", []) if isinstance(audits_data, dict) else []
                        ):
                            aid = audit.get("ActivityInstanceID")
                            if aid and aid not in unique_acts:
                                unique_acts[aid] = datetime.fromisoformat(
                                    audit["TimeStamp"]
                                ).strftime("%Y-%m-%d %H:%M:%S")
                        history_list = []
                        total = len(unique_acts)
                        for i, (aid, ts) in enumerate(unique_acts.items()):
                            name = get_activity_type_name(aid, domain)
                            history_list.append(
                                {"Activity": name, "DateTime": ts, "Step": total - i}
                            )
                        cache.set(
                            _wi_cache_key("audithistory", wid, domain), history_list, timeout=1800
                        )
                        detail["history"] = history_list
                except Exception as e:
                    _app.logger.error(f"Export: history error for {wid}: {e}")
        return (client, wid), detail

    details_map = {}
    any_timed_out = False
    if include_fields or include_history or include_images:
        max_workers = min(10, len(workitems))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch, w["workitemid"], w.get("client")): (
                    w.get("client"),
                    w["workitemid"],
                )
                for w in workitems
            }
            try:
                for future in as_completed(futures, timeout=120):
                    try:
                        key, detail = future.result()
                        details_map[key] = detail
                    except Exception as e:
                        key = futures[future]
                        _app.logger.error(f"Export: future error for {key}: {e}")
                        details_map[key] = {"fields": {}, "history": [], "images": []}
            except concurrent.futures.TimeoutError:
                # as_completed() itself raises this at the loop's iteration
                # boundary once the 120s budget elapses with futures still
                # pending -- distinct from a per-future error, which is
                # already handled above. Cancelling is best-effort (threads
                # already running won't actually stop); we don't wait for it.
                # Whatever finished stays in details_map; the rest get an
                # explicit timed-out marker so the export still degrades to
                # a valid, honest CSV instead of a 500.
                pending = [key for key in futures.values() if key not in details_map]
                _app.logger.error(
                    f"Export: as_completed timed out after 120s with "
                    f"{len(pending)} workitem(s) still pending: {pending}"
                )
                any_timed_out = True
                for future, key in futures.items():
                    if key not in details_map:
                        future.cancel()
                        details_map[key] = {
                            "fields": {},
                            "history": [],
                            "images": [],
                            "timed_out": True,
                        }

    if include_fields:
        _strip_export_fields(details_map, sensitive_blocked_tokens())

    all_field_keys = []
    if include_fields:
        seen_keys = set()
        for w in workitems:
            for k in details_map.get((w.get("client"), w["workitemid"]), {}).get("fields", {}):
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_field_keys.append(k)

    max_images = 0
    if include_images:
        for w in workitems:
            max_images = max(
                max_images,
                len(details_map.get((w.get("client"), w["workitemid"]), {}).get("images", [])),
            )

    # D-CSVTIMEOUT: all_field_keys/max_images are derived from whichever rows
    # actually completed before the as_completed() timeout above. If the 120s
    # budget elapsed before ANY future completed (a real Octo-outage shape --
    # EXPORT_HEAVY_INCLUDE_MAX_IDS caps heavy exports to <=10 rows, so "nothing
    # finished in time" is plausible, not just theoretical), both end up
    # empty/zero and the CSV carries no include= columns at all -- the
    # per-row EXPORT_TIMEOUT_MARKER has nowhere to go, since there are no
    # columns to put it in. That makes a timeout-degraded export
    # indistinguishable from a legitimate "these workitems have no
    # fields/images" result. Flag it so it can be surfaced the same way
    # row-truncation already is, below.
    timeout_degraded_headers = any_timed_out and (
        (include_fields and not all_field_keys) or (include_images and max_images == 0)
    )

    headers = ["Workitem ID", "Status", "Stage", "Last Movement At"]
    if include_fields:
        headers.extend(all_field_keys)
    if include_history:
        headers.append("Audit History")
    if include_images:
        headers.extend(f"Image {i+1} (base64)" for i in range(max_images))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for w in workitems:
        wid = w["workitemid"]
        detail = details_map.get(
            (w.get("client"), wid), {"fields": {}, "history": [], "images": []}
        )
        ts = w.get("modifiedat")
        date_str = (
            ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "")[:19]
        )

        row = [
            wid,
            w.get("status", ""),
            w.get("current_stage", ""),
            date_str,
        ]
        # Rows still pending when as_completed() hit its timeout carry an
        # explicit marker in every include= column rather than blank data
        # that would be indistinguishable from "no data found".
        timed_out = detail.get("timed_out", False)
        if include_fields:
            if timed_out:
                row.extend(EXPORT_TIMEOUT_MARKER for _ in all_field_keys)
            else:
                fields = detail["fields"]
                row.extend(fields.get(k, "") for k in all_field_keys)
        if include_history:
            if timed_out:
                row.append(EXPORT_TIMEOUT_MARKER)
            else:
                history = sorted(
                    detail.get("history", []), key=lambda h: h.get("Step", 0), reverse=True
                )
                row.append(
                    "; ".join(
                        f"Step {h['Step']}: {h['Activity']} @ {h['DateTime']}" for h in history
                    )
                )
        if include_images:
            if timed_out:
                row.extend(EXPORT_TIMEOUT_MARKER for _ in range(max_images))
            else:
                images = detail.get("images", [])
                row.extend(images[i] if i < len(images) else "" for i in range(max_images))
        writer.writerow(row)

    csv_content = output.getvalue()
    if truncated:
        # Never let an export look complete when it is not.
        csv_content += (
            f"\r\n# {_('TRUNCATED')}: "
            f"{_('exported')} {len(workitems)} / {matched_total} {_('matching workitems')}\r\n"
        )
    if timeout_degraded_headers:
        # Never let a timeout-degraded export (zero completed rows) look like
        # a legitimate zero-fields/zero-images result.
        csv_content += (
            f"\r\n# {_('EXPORT TIMED OUT')}: "
            f"{_('no fields or images completed before the time limit; this is not a zero-result export')}\r\n"
        )
    response = make_response(csv_content)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    if truncated:
        response.headers["X-Export-Truncated"] = f"{len(workitems)}/{matched_total}"
    if timeout_degraded_headers:
        response.headers["X-Export-Timeout"] = "true"
    filename = f'workitems_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@require_permission("workitems.view")
def workitems_overview():
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get("username")
        userid = session.get("userid")

        search_term_perm = has_permission("workitems.filter.workitemid")
        search_term = request.args.get("search", "").strip() if search_term_perm else None

        status_perm = has_permission("workitems.filter.status")
        status = request.args.get("status", "") if status_perm else None
        deleted_status_perm = status_perm and has_permission("workitems.filter.status.deleted")

        stage_perm = has_permission("workitems.filter.stage")
        stage = request.args.get("stage", "") if stage_perm else None

        datetime_perm = has_permission("workitems.filter.datetime")
        start_date_str = request.args.get("startDate", "") if datetime_perm else None
        end_date_str = request.args.get("endDate", "") if datetime_perm else None
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else None

        perms = session.get("permissions", [])
        prefix = "workitems.filter.process."
        allowed_processes = sorted(
            {
                (perm.split(".")[-2] + "." + perm.split(".")[-1])
                for perm in perms
                if perm.startswith(prefix)
            }
        )

        process_name = request.args.get("prcfW", "all")
        if process_name != "all" and process_name not in allowed_processes:
            process_name = "all"

        doc_fields_values_perm = has_permission("workitems.filter.documentfields")
        docfields = request.args.getlist("docfield") if doc_fields_values_perm else None
        docvalues = request.args.getlist("docvalue") if doc_fields_values_perm else None
        docops = request.args.getlist("docop") if doc_fields_values_perm else None

        details_view_perm = has_permission("workitems.details.view")
        details_images_perm = has_permission("workitems.details.view.images")
        details_audit_perm = has_permission("workitems.details.view.audit")
        details_fields_perm = has_permission("workitems.details.view.fields")

        prepared_import_perm = has_permission("workitems.import.preparedaudit")
        ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None

        # The Prepared Documents toolbar link is rendered whenever the user holds
        # the perm + MS02 is active, but is shown only for the PDBS prepared-docs
        # processes. The process dropdown updates the page via AJAX (no full
        # reload), so JS toggles the link live from ms02_pdoc_processes when the
        # dropdown changes; prepared_docs_process_match is just the initial state.
        ms02_pdoc_processes = (
            _ms02_prepared_docs_processes() if (ms02_active and prepared_import_perm) else []
        )
        prepared_docs_process_match = process_name in ms02_pdoc_processes

        return render_template(
            "workitems_overview.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            search=search_term,
            status=status,
            stage=stage,
            start_date=start_date,
            end_date=end_date,
            docfield=docfields[0] if docfields else "",
            docvalue=docvalues[0] if docvalues else "",
            docop=docops[0] if docops else "contains",
            page_visibility=page_visibility(),
            allowed_processes=allowed_processes,
            search_term_perm=search_term_perm,
            status_perm=status_perm,
            deleted_status_perm=deleted_status_perm,
            stage_perm=stage_perm,
            workitem_stages=WORKITEM_STAGES,
            datetime_perm=datetime_perm,
            doc_fields_values_perm=doc_fields_values_perm,
            details_view_perm=details_view_perm,
            details_images_perm=details_images_perm,
            details_audit_perm=details_audit_perm,
            details_fields_perm=details_fields_perm,
            prepared_import_perm=prepared_import_perm,
            ms02_active=ms02_active,
            prepared_docs_process_match=prepared_docs_process_match,
            ms02_pdoc_processes=ms02_pdoc_processes,
        )
    except Exception:
        return render_template("500.html")


@require_permission("workitems.import.workitem")
def import_workitems():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    if "importFile" not in request.files:
        flash(_("No file part in the request."), "error")
        return redirect(url_for("workitems_overview"))

    file = request.files["importFile"]
    process_name = request.form.get("processName")

    if file.filename == "":
        flash(_("No file selected for uploading."), "error")
        return redirect(url_for("workitems_overview"))

    if not process_name:
        flash(_("No target process selected."), "error")
        return redirect(url_for("workitems_overview"))

    perms = session.get("permissions", [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split(".")[-2] + "." + perm.split(".")[-1])
        for perm in perms
        if perm.startswith(prefix)
    }

    if process_name not in allowed_processes:
        flash(_("You do not have permission to import to this process."), "error")
        return redirect(url_for("workitems_overview"))

    if file and is_file_allowed(file.filename, file.stream):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{session.get('username')}_{filename}"

        process_upload_folder = PATHS.uploads / process_name.replace(".", "_")
        process_upload_folder.mkdir(parents=True, exist_ok=True)

        file_path = process_upload_folder / unique_filename

        try:
            file.save(file_path)
            flash(
                _("File '{}' successfully imported into {}.").format(filename, process_name),
                "success",
            )
        except Exception as e:
            current_app.logger.error(f"Error saving imported file: {e}")
            flash(_("An error occurred while saving the file."), "error")
    else:
        flash(_("Invalid file type. Please upload a valid PDF."), "error")

    return redirect(url_for("workitems_overview"))


@require_permission("workitems.import.preparedaudit")
def import_prepared_audit():
    """MS02-only: upload a five-column Excel (PID, Collected, CollectedBy,
    Prepared, PreparedBy) and UPSERT each row by PID into the persistent
    dbo.PreparedDocuments register (one row per PID; re-uploading a PID updates
    its row). Returns {inserted, updated, total}. The register is shared across
    MS02 users and viewed on the /prepared_documents page (this route no longer
    resolves PIDs to workitem ids or stashes anything in the session). Rows
    persist regardless of whether the PID column is configured -- the live Octo
    status on the page degrades to a dash when it cannot resolve."""
    # Defensive parity with import_workitems (require_permission already gates
    # auth, redirecting unauthenticated users to login; this never 401s a gated
    # caller -- it is dead-code parity, not a tested path).
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    # MS02-only gate: no MS02 doc-field engine / no ms02 client -> not available.
    if engine_ms02_docfields_pg is None or "ms02" not in CLIENTS:
        return jsonify({"error": _("This import is only available for the MS02 client.")}), 400

    if "preparedAuditFile" not in request.files:
        return jsonify({"error": _("No file part in the request.")}), 400
    file = request.files["preparedAuditFile"]
    if not file or file.filename == "":
        return jsonify({"error": _("No file selected for uploading.")}), 400

    if not is_file_allowed(file.filename, file.stream):
        return jsonify(
            {"error": _("Invalid file type. Please upload a valid Excel (.xlsx) file.")}
        ), 400

    data = file.stream.read()
    pairs, parse_err = parse_prepared_xlsx(data)
    if parse_err:
        return jsonify({"error": parse_err}), 400
    if not pairs:
        return jsonify({"error": _("The Excel file has no usable rows.")}), 400

    rows = [
        {
            "pid": row["pid"],
            "collected": row["collected"],
            "collected_by": row["collected_by"],
            "prepared": row["prepared"],
            "prepared_by": row["prepared_by"],
        }
        for row in pairs
    ]

    try:
        result = upsert_prepared_documents(rows, session.get("userid"))
    except RuntimeError:
        return jsonify(
            {"error": _("Could not save the prepared documents. Please try again.")}
        ), 500
    return jsonify(result), 200


def api_get_media_info(workitem_id):
    if not has_permission("workitems.details.view"):
        return jsonify({"error": _("Not authorized")}), 403
    if not _may_view_workitem(workitem_id):
        return jsonify({"error": _("Not authorized")}), 403
    try:
        can_view_images = has_permission("workitems.details.view.images")
        can_view_fields = has_permission("workitems.details.view.fields")
        can_view_confidence = has_permission("workitems.details.view.confidence")
        # Source-location boxes are drawn over the page image, so the location data
        # needs BOTH the dedicated location perm AND images (no image -> nothing to
        # draw on / broken click-to-locate).
        can_view_location = can_view_images and has_permission(
            "workitems.details.view.source_location"
        )

        def _suppress(data):
            # Granular per-permission suppression (returns a copy so the cached
            # object is never mutated):
            #   fields                    -> see the extracted values at all
            #   images + source_location  -> see WHERE on the page (boxes + locate)
            #   confidence                -> see the extraction confidence %
            d = data.copy()
            # lets the front-end suppress the "no source location" badge when the
            # perm is absent (vs. a value that genuinely has no location).
            d["source_location_visible"] = can_view_location
            d["confidence_visible"] = can_view_confidence
            if not can_view_images:
                d["media_count"] = 0
            if not can_view_fields:
                d["fields"] = {}
                d["field_sources"] = []
                d["table_sources"] = []
                return d
            blocked_sensitive = sensitive_blocked_tokens()
            if blocked_sensitive:
                d = strip_sensitive_from_detail(d, blocked_sensitive)
            fs = d.get("field_sources", [])
            ts = d.get("table_sources", [])
            if not can_view_location:
                fs = [{**s, "locations": []} for s in fs]
                ts = [
                    {
                        **t,
                        "rows": [
                            [{**c, "locations": []} for c in row] for row in t.get("rows", [])
                        ],
                    }
                    for t in ts
                ]
            if not can_view_confidence:
                fs = [{k: v for k, v in s.items() if k != "confidence"} for s in fs]
                ts = [
                    {
                        **t,
                        "rows": [
                            [{k: v for k, v in c.items() if k != "confidence"} for c in row]
                            for row in t.get("rows", [])
                        ],
                    }
                    for t in ts
                ]
            d["field_sources"] = fs
            d["table_sources"] = ts
            return d

        # Workitem ids are NOT globally unique across clients (1216 collide on
        # INT), so both the routing and every cache key must carry the client
        # the row came from -- otherwise one client's document is served, and
        # then cached, for the other client's identically numbered workitem.
        client_hint = _client_hint()
        domain = get_domain_for_workitem(workitem_id, client_hint=client_hint)
        response_data = _load_media_info(workitem_id, domain)
        if response_data is None:
            return jsonify({"error": _("Workitem not found")}), 404
        return jsonify(_suppress(response_data))
    except Exception as e:
        print(f"An error occurred in get_media_info: {e}")
        return jsonify({"error": _("Internal Server Error")}), 500


# nx_lib.workitems.media.load_media_info is the Flask-free core (D4); this
# wrapper keeps the historical 0-arg-besides-(workitem_id, domain) signature
# and reads Octo/cache off this module's OWN globals (get_workitemdata_param,
# get_extensions_urls_fields, cache) so every existing monkeypatch-based test
# that patches those names on nx_lib.views.workitems keeps working unchanged.
def _load_media_info(workitem_id, domain):
    return _load_media_info_core(
        workitem_id,
        domain,
        get_workitemdata_param=get_workitemdata_param,
        get_extensions_urls_fields=get_extensions_urls_fields,
        cache=cache,
    )


@require_permission("workitems.details.view.images")
def api_get_media_raw(workitem_id, media_index):
    if not _may_view_workitem(workitem_id):
        return Response(_("Not authorized"), status=403)
    try:
        domain = get_domain_for_workitem(workitem_id, client_hint=_client_hint())
        _ck = _wi_cache_key("media_data", workitem_id, domain)
        media_data = cache.get(_ck)
        if not media_data:
            returndata = get_workitemdata_param(workitem_id, domain)
            if not returndata:
                return Response(_("Workitem not found"), status=404)

            workitemdata, document_id = returndata
            extensions, urls, fields, _fs, _ts = get_extensions_urls_fields(
                workitemdata, document_id, domain
            )
            media_data = {"extensions": extensions, "urls": urls}
            cache.set(_ck, media_data)

        extensions = media_data.get("extensions", [])
        urls = media_data.get("urls", [])

        if media_index >= len(urls):
            return Response(_("Media index out of bounds"), status=404)

        target_url = urls[media_index]
        target_extension = extensions[media_index].lower()

        if target_extension == ".pdf":
            # PDF media is expanded one slot per page (page in the URL fragment).
            # Rasterise the requested page to JPEG, cached per (workitem, slot).
            _pdf_cache_key = _wi_cache_key(f"media_raw_pdfpage_{media_index}", workitem_id, domain)
            cached_jpeg = cache.get(_pdf_cache_key)
            if cached_jpeg is not None:
                resp = send_file(
                    io.BytesIO(cached_jpeg), mimetype="image/jpeg", as_attachment=False
                )
                resp.headers["Cache-Control"] = "private, max-age=3600"
                return resp
            base_url, _sep, frag = target_url.partition("#")
            page_index = 0
            if frag.startswith("page="):
                try:
                    page_index = int(frag[len("page=") :])
                except ValueError:
                    page_index = 0
            try:
                pdf_bytes = pdf_src_bytes(base_url, domain)
                jpeg_bytes = render_pdf_page_jpeg(pdf_bytes, page_index)
            except Exception as e:
                print(f"PDF page render failed: {e}")
                return _("Failed to render PDF page"), 500
            cache.set(_pdf_cache_key, jpeg_bytes, timeout=3600)
            resp = send_file(io.BytesIO(jpeg_bytes), mimetype="image/jpeg", as_attachment=False)
            resp.headers["Cache-Control"] = "private, max-age=3600"
            return resp

        if target_extension == ".tif":
            _tif_cache_key = _wi_cache_key(f"media_raw_tif_{media_index}", workitem_id, domain)
            cached_jpeg = cache.get(_tif_cache_key)
            if cached_jpeg is not None:
                resp = send_file(
                    io.BytesIO(cached_jpeg), mimetype="image/jpeg", as_attachment=False
                )
                resp.headers["Cache-Control"] = "private, max-age=3600"
                return resp

            raw_media_bytes = get_media(target_url, domain)
            try:
                image_stream = io.BytesIO(raw_media_bytes)
                with Image.open(image_stream) as img:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=85)
                    jpeg_bytes = buffer.getvalue()
                    cache.set(_tif_cache_key, jpeg_bytes, timeout=3600)
                    resp = send_file(
                        io.BytesIO(jpeg_bytes), mimetype="image/jpeg", as_attachment=False
                    )
                    resp.headers["Cache-Control"] = "private, max-age=3600"
                    return resp
            except Exception as e:
                print(f"An error occurred during TIFF conversion: {e}")
                return _("Failed to process TIFF image"), 500

        if target_extension == ".jpg":
            mimetype = "image/jpeg"
        elif target_extension == ".png":
            mimetype = "image/png"
        else:
            mimetype = "application/octet-stream"

        # JPG/PNG media streamed straight from Octo, same as the PDF/TIFF
        # branches above -- cache the raw bytes server-side so a re-opened
        # detail panel (or a second viewer) doesn't re-fetch from Octo.
        _img_cache_key = _wi_cache_key(f"media_raw_img_{media_index}", workitem_id, domain)
        raw_media_bytes = cache.get(_img_cache_key)
        if raw_media_bytes is None:
            raw_media_bytes = get_media(target_url, domain)
            cache.set(_img_cache_key, raw_media_bytes, timeout=3600)

        response = make_response(raw_media_bytes)
        response.headers.set("Content-Type", mimetype)
        response.headers.set("Cache-Control", "private, max-age=3600")
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return Response(_("Internal Server Error"), status=500)


@require_permission("workitems.details.view.audit")
def get_audithistory(workitem_id):
    if not _may_view_workitem(workitem_id):
        return jsonify({"error": _("Not authorized")}), 403
    domain = get_domain_for_workitem(workitem_id, client_hint=_client_hint())
    _cache_key = _wi_cache_key("audithistory", workitem_id, domain)
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        audit_url = (
            f"https://{domain}/api/processservice/api/v2.1/processService/WorkItemAudits"
            f"?WorkItemID={workitem_id}&VerifyAuditSignatures=true&ExportSignatureVerificationCertificates=true"
        )
        access_token = get_access_token(domain)
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url=audit_url, headers=headers, timeout=10)
        response.raise_for_status()
        audits = response.json()
        if not audits or not isinstance(audits, dict):
            return jsonify([])
        unique_activities = {}
        for audit in audits.get("Audits", []):
            activity_id = audit.get("ActivityInstanceID")
            if activity_id and activity_id not in unique_activities:
                unique_activities[activity_id] = datetime.fromisoformat(
                    audit["TimeStamp"]
                ).strftime("%Y-%m-%d %H:%M:%S")

        total_steps = len(unique_activities)
        activity_ids = list(unique_activities.keys())
        # get_activity_type_name is memoized, but a cold cache (first time an
        # activity is seen) still means one Octo round trip per step -- fetch
        # cold misses concurrently instead of sum-of-latencies.
        _app = current_app._get_current_object()

        def _name_for(activity_id):
            with _app.app_context():
                return activity_id, get_activity_type_name(activity_id, domain)

        names = {}
        if activity_ids:
            with ThreadPoolExecutor(max_workers=min(10, len(activity_ids))) as executor:
                for future in as_completed(executor.submit(_name_for, aid) for aid in activity_ids):
                    aid, name = future.result()
                    names[aid] = name

        complete_array = [
            {
                "Activity": names.get(activity_id, "Unknown Activity"),
                "DateTime": time_stamp,
                "Step": total_steps - i,
            }
            for i, (activity_id, time_stamp) in enumerate(unique_activities.items())
        ]

        cache.set(_cache_key, complete_array, timeout=1800)
        return jsonify(complete_array)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"{_('Failed to fetch audit history')}: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"{_('An unexpected error occurred')}: {e}"}), 500


def api_workitems_page_init():
    if "username" not in session:
        return jsonify({}), 401

    perms = session.get("permissions", [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split(".")[-2] + "." + perm.split(".")[-1])
        for perm in perms
        if perm.startswith(prefix)
    }
    current_lang = str(get_locale())
    _sees_sensitive = has_permission("workitems.filter.documentfields.sensitive")
    _fields_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}_s{int(_sees_sensitive)}"
    field_config = cache.get(_fields_key)
    if field_config is None:
        search_options, db_labels_map = _build_field_config(allowed_processes, current_lang)
        blocked = sensitive_blocked_keys()
        if blocked:
            search_options = drop_sensitive_options(search_options, blocked)
            db_labels_map = {k: v for k, v in db_labels_map.items() if k.lower() not in blocked}
        field_config = {"search_options": search_options, "labels": db_labels_map}
        cache.set(_fields_key, field_config, timeout=3600)

    return jsonify({"field_config": field_config})


def _resolve_prepared_doc_wid_stage(wid):
    """dbo.PreparedDocuments is an MS02-only register (see prepared_documents's
    ms02_active gate), so every visible wid is owned by the 'ms02' client's
    runtime -- never the default one. Workitem identity is (client, id) and
    ids collide across runtimes (docs/design/ms02-multisource.md): resolving
    against CLIENTS['default'] can silently surface a DIFFERENT client's
    status/stage for a colliding id. Dialect-safe: resolve_octo_wid_stage is
    SQL-Server-shaped, so route through the Postgres-side twin when the
    owning client's dialect says so. Fails closed (empty stage -> in_octo=
    False) on any lookup/resolution error -- a bad wid or malformed CLIENTS
    entry must never raise and 500 the register page."""
    empty = {"status": None, "current_stage": None}
    try:
        client = CLIENTS.get("ms02")
        if client is None:
            return empty
        if client.dialect == "postgres":
            return _resolve_octo_wid_stage_pg(client.runtime_engine, wid)
        return resolve_octo_wid_stage(client.runtime_engine, wid)
    except Exception as e:
        current_app.logger.error(f"_resolve_prepared_doc_wid_stage({wid}): {e}")
        return empty


@require_permission("workitems.import.preparedaudit")
def prepared_documents():
    """MS02-only standalone 'prepared documents' register page. Reads a real
    OFFSET/FETCH page of dbo.PreparedDocuments and resolves a live (non-stored)
    Octo cross-reference status for the visible PIDs via resolve_ms02_pid_to_wids.
    Read-only + clear-whole-list for v1."""
    ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
    if not ms02_active:
        raise PermissionDenied(_("This page is only available for the MS02 client."))

    try:
        per_page = int(request.args.get("per_page", 40))
    except (TypeError, ValueError):
        per_page = 40
    if per_page not in (25, 40, 100, 200):
        per_page = 40
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * per_page

    pid_filter = (request.args.get("pid") or "").strip() or None

    def _bool_arg(name):
        val = request.args.get(name)
        return {"1": True, "0": False}.get(val)

    collected_filter = _bool_arg("collected")
    prepared_filter = _bool_arg("prepared")
    group_by = request.args.get("group_by") or None
    if group_by not in GROUP_BY_COLUMNS:
        group_by = None

    try:
        total_items = count_prepared_documents(
            pid=pid_filter, collected=collected_filter, prepared=prepared_filter
        )
        rows = fetch_prepared_documents_page(
            offset,
            per_page,
            pid=pid_filter,
            collected=collected_filter,
            prepared=prepared_filter,
            group_by=group_by,
        )
    except Exception as e:
        current_app.logger.error(f"prepared_documents read: {e}")
        total_items, rows = 0, []

    # Live Octo soft-status for the visible page's PIDs (never stored; degrade to
    # a dash on None/empty/error -- resolve_ms02_pid_to_wids never raises).
    octo_status = {}
    pids = [r["pid"] for r in rows if r["pid"]]
    if pids:
        pid_specs = _ms02_pid_specs(_ms02_target_processes())
        pid_to_wids = (
            resolve_ms02_pid_to_wids(engine_ms02_docfields_pg, pid_specs, pids)
            if pid_specs
            else None
        )
        if pid_to_wids:
            for pid, wids in pid_to_wids.items():
                if wids:
                    wid = wids[0]
                    stage = _resolve_prepared_doc_wid_stage(wid)
                    octo_status[pid] = {
                        "in_octo": bool(stage and stage.get("status")),
                        "wid": wid,
                        "status": stage["status"] or "",
                        "current_stage": stage["current_stage"] or "",
                    }

    total_pages = math.ceil(total_items / per_page) if per_page else 0
    pagination = {
        "currentPage": page,
        "totalPages": total_pages,
        "totalItems": total_items,
        "perPage": per_page,
    }
    # Non-page filter/sort state, carried through the Previous/Next links so
    # paging never silently drops the active filters.
    filter_args = {}
    if pid_filter:
        filter_args["pid"] = pid_filter
    if collected_filter is not None:
        filter_args["collected"] = "1" if collected_filter else "0"
    if prepared_filter is not None:
        filter_args["prepared"] = "1" if prepared_filter else "0"
    if group_by:
        filter_args["group_by"] = group_by
    if per_page != 40:
        filter_args["per_page"] = str(per_page)

    details_view_perm = has_permission("workitems.details.view")
    details_images_perm = has_permission("workitems.details.view.images")
    details_audit_perm = has_permission("workitems.details.view.audit")
    details_fields_perm = has_permission("workitems.details.view.fields")

    return render_template(
        "prepared_documents.html",
        rows=rows,
        pagination=pagination,
        octo_status=octo_status,
        pid_filter=pid_filter,
        collected_filter=collected_filter,
        prepared_filter=prepared_filter,
        group_by=group_by,
        filter_args=filter_args,
        prepared_import_perm=has_permission("workitems.import.preparedaudit"),
        ms02_active=ms02_active,
        page_visibility=page_visibility(),
        details_view_perm=details_view_perm,
        details_images_perm=details_images_perm,
        details_audit_perm=details_audit_perm,
        details_fields_perm=details_fields_perm,
        userid=session.get("userid"),
    )


@require_permission("workitems.import.preparedaudit")
def clear_prepared_documents_route():
    """MS02-only: delete every row in the prepared-documents register."""
    ms02_active = "ms02" in CLIENTS and engine_ms02_docfields_pg is not None
    if not ms02_active:
        return jsonify({"error": _("This import is only available for the MS02 client.")}), 400
    try:
        deleted = clear_prepared_documents()
    except Exception as e:
        current_app.logger.error(f"clear_prepared_documents_route: {e}")
        return jsonify(
            {"error": _("Could not clear the prepared documents. Please try again.")}
        ), 500
    return jsonify({"deleted": deleted}), 200


# ------------------------- saved filter views (#170) ------------------------- #

MAX_FILTER_VIEWS = 50


def _validate_filter_view(payload):
    """Returns (name, folder, filters_json). Raises ValueError on bad input.

    `filters` is the client's [name, value] pair list — the same serialization
    the page sends to /api/workitems. Stored opaquely; the server never applies
    it, so per-field permission gates keep working unchanged on replay.
    `folder` is the optional grouping category (#186); empty/blank -> NULL.
    """
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ValueError("name")
    folder = payload.get("folder") or ""
    if not isinstance(folder, str) or len(folder) > 100:
        raise ValueError("folder")
    folder = folder.strip() or None
    filters = payload.get("filters")
    if not isinstance(filters, list) or len(filters) > 60:
        raise ValueError("filters")
    for pair in filters:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(x, str) for x in pair)
            or len(pair[0]) > 100
            or len(pair[1]) > 1000
        ):
            raise ValueError("filters")
    return name, folder, json.dumps(filters)


@require_permission("workitems.view")
def api_workitem_filter_views():
    """List the current user's saved filter views."""
    conn = engine_nexora_db.raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ID, Name, Folder, FilterJSON FROM WorkitemFilterViews"
            " WHERE UserID = ? ORDER BY SortOrder, Name",
            (session["userid"],),
        )
        views = []
        for row in cursor.fetchall():
            try:
                filters = json.loads(row.FilterJSON)
            except ValueError:
                filters = []
            views.append({"id": row.ID, "name": row.Name, "folder": row.Folder, "filters": filters})
        return jsonify({"views": views})
    except Exception as e:
        current_app.logger.error(f"api_workitem_filter_views: {e}")
        return jsonify({"error": _("Could not load saved views.")}), 500
    finally:
        conn.close()


@require_permission("workitems.view")
def save_workitem_filter_view():
    """Create or update a saved view. Without `id`, saving under an existing
    name overwrites that view's filters + folder; with `id`, updates name,
    folder and filters (rename/move keeps the id stable)."""
    payload = request.get_json(silent=True) or {}
    try:
        name, folder, filters_json = _validate_filter_view(payload)
    except ValueError:
        return jsonify({"error": _("Invalid view name or filters.")}), 400
    view_id = payload.get("id")
    if view_id is not None and not isinstance(view_id, int):
        return jsonify({"error": _("Invalid view name or filters.")}), 400

    userid = session["userid"]
    conn = engine_nexora_db.raw_connection()
    try:
        cursor = conn.cursor()
        if view_id is not None:
            cursor.execute(
                "UPDATE WorkitemFilterViews SET Name = ?, Folder = ?, FilterJSON = ?"
                " WHERE ID = ? AND UserID = ?",
                (name, folder, filters_json, view_id, userid),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"error": _("View not found.")}), 404
        else:
            cursor.execute(
                "UPDATE WorkitemFilterViews SET Folder = ?, FilterJSON = ?"
                " WHERE UserID = ? AND Name = ?",
                (folder, filters_json, userid, name),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "SELECT COUNT(*) FROM WorkitemFilterViews WHERE UserID = ?", (userid,)
                )
                if cursor.fetchone()[0] >= MAX_FILTER_VIEWS:
                    conn.rollback()
                    return jsonify({"error": _("Too many saved views — delete one first.")}), 400
                cursor.execute(
                    "INSERT INTO WorkitemFilterViews (UserID, Name, Folder, FilterJSON)"
                    " VALUES (?, ?, ?, ?)",
                    (userid, name, folder, filters_json),
                )
            cursor.execute(
                "SELECT ID FROM WorkitemFilterViews WHERE UserID = ? AND Name = ?",
                (userid, name),
            )
            view_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({"id": view_id, "name": name, "folder": folder})
    except pyodbc.IntegrityError:
        conn.rollback()
        return jsonify({"error": _("A view with this name already exists.")}), 400
    except Exception as e:
        current_app.logger.error(f"save_workitem_filter_view: {e}")
        return jsonify({"error": _("Could not save the view.")}), 500
    finally:
        conn.close()


@require_permission("workitems.view")
def delete_workitem_filter_view(view_id):
    """Delete one of the current user's saved views."""
    conn = engine_nexora_db.raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM WorkitemFilterViews WHERE ID = ? AND UserID = ?",
            (view_id, session["userid"]),
        )
        deleted = cursor.rowcount
        conn.commit()
        if not deleted:
            return jsonify({"error": _("View not found.")}), 404
        return jsonify({"deleted": deleted})
    except Exception as e:
        current_app.logger.error(f"delete_workitem_filter_view: {e}")
        return jsonify({"error": _("Could not delete the view.")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/config/fields", endpoint="api_config_fields", view_func=api_config_fields
    )
    app.add_url_rule(
        "/api/docfield_values", endpoint="api_docfield_values", view_func=api_docfield_values
    )
    app.add_url_rule("/api/workitems", endpoint="api_workitems", view_func=api_workitems)
    app.add_url_rule(
        "/api/export/workitems/csv", endpoint="export_workitems_csv", view_func=export_workitems_csv
    )
    app.add_url_rule("/workitems", endpoint="workitems_overview", view_func=workitems_overview)
    app.add_url_rule(
        "/import_workitems",
        endpoint="import_workitems",
        view_func=import_workitems,
        methods=["POST"],
    )
    app.add_url_rule(
        "/import_prepared_audit",
        endpoint="import_prepared_audit",
        view_func=import_prepared_audit,
        methods=["POST"],
    )
    app.add_url_rule(
        "/prepared_documents",
        endpoint="prepared_documents",
        view_func=prepared_documents,
        methods=["GET"],
    )
    app.add_url_rule(
        "/prepared_documents/clear",
        endpoint="clear_prepared_documents_route",
        view_func=clear_prepared_documents_route,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/get_media_info/<int:workitem_id>",
        endpoint="api_get_media_info",
        view_func=api_get_media_info,
    )
    app.add_url_rule(
        "/api/get_media_raw/<int:workitem_id>/<int:media_index>",
        endpoint="api_get_media_raw",
        view_func=api_get_media_raw,
    )
    app.add_url_rule(
        "/api/get_audithistory/<int:workitem_id>",
        endpoint="get_audithistory",
        view_func=get_audithistory,
    )
    app.add_url_rule(
        "/api/workitems_page_init",
        endpoint="api_workitems_page_init",
        view_func=api_workitems_page_init,
    )
    app.add_url_rule(
        "/api/workitem_filter_views",
        endpoint="api_workitem_filter_views",
        view_func=api_workitem_filter_views,
    )
    app.add_url_rule(
        "/api/workitem_filter_views",
        endpoint="save_workitem_filter_view",
        view_func=save_workitem_filter_view,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/workitem_filter_views/<int:view_id>",
        endpoint="delete_workitem_filter_view",
        view_func=delete_workitem_filter_view,
        methods=["DELETE"],
    )
