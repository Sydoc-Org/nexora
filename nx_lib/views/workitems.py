"""Workitems: list, detail, media, audit, comments, tags, priority, assignment,
plus the CSV exporter."""

import base64
import csv
import io
import json
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

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

from ..config import DB_NEXORA, DB_STATISTICS, OCTO_DOMAIN, PATHS
from ..db import engine_nexora_db, engine_octo_db, engine_statistics_db
from ..extensions import cache
from ..files import is_file_allowed
from ..i18n import get_locale
from ..notifications import create_notification
from ..octo import (
    get_access_token,
    get_activity_type_name,
    get_domain_for_workitem,
    get_extensions_urls_fields,
    get_media,
    get_workitemdata_param,
)
from ..process_helpers import (
    get_activity_instances_to_ignore,
    prepare_process_selection_sql,
)
from ..security import has_permission, page_visibility, require_permission
from ..users import get_all_portal_users, resolve_user_icon_url

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
    _cache_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)
    lang_column_map = {
        "de": "GermanLabel",
        "fr": "FrenchLabel",
        "it": "ItalianLabel",
        "en": "EnglishLabel",
    }
    target_column = lang_column_map.get(current_lang, "EnglishLabel")

    search_options = {}
    db_labels_map = {}
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels"
            )
            for row in cursor.fetchall():
                translated_label = getattr(row, target_column) or row.EnglishLabel
                db_labels_map[row.FieldKey] = translated_label
        except Exception:
            pass

        cursor.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cursor.description if c[0].startswith("col_")]

        query = f"SELECT ProcessName, {','.join(cols)} FROM SearchConfig"
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            proc_name = row.ProcessName

            if proc_name not in allowed_processes:
                continue

            fields = []
            for i, col_name in enumerate(cols):
                if row[i + 1]:
                    field_key = col_name.replace("col_", "")
                    nice_label = db_labels_map.get(field_key, field_key.replace("_", " ").title())

                    fields.append(
                        {
                            "value": field_key,
                            "label": nice_label,
                        }
                    )
            fields.sort(key=lambda x: x["label"])
            search_options[proc_name] = fields

    except Exception as e:
        current_app.logger.error(f"Error fetching field config: {e}")
    finally:
        if conn:
            conn.close()

    result = {"search_options": search_options, "labels": db_labels_map}
    cache.set(_cache_key, result, timeout=3600)
    return jsonify(result)


@cache.cached(timeout=3600, key_prefix="search_config_columns")
def get_valid_search_columns():
    conn = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 0 * FROM SearchConfig")
        valid_cols = [c[0].lower() for c in cursor.description if c[0].lower().startswith("col_")]
        return valid_cols
    except Exception as e:
        current_app.logger.error(f"Error fetching search config columns: {e}")
        return []
    finally:
        if conn:
            conn.close()


def _get_workitems_data(args, export_all=False):
    page = args.get("page", 1, type=int)
    search_term = args.get("search", "").strip()
    status = args.get("status", "")
    tag_filter = args.get("tag", "").strip()
    start_date_str = args.get("startDate", "")
    end_date_str = args.get("endDate", "")
    start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
    end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
    priority = args.get("priority", "")
    assigned_user = args.get("assignedUser", "")
    if export_all:
        per_page = 5000
        offset = 0
    else:
        per_page = int(args.get("perPage", 40))
        if per_page not in (40, 100, 200, 500, 1000):
            per_page = 40
        offset = (page - 1) * per_page
    activity_instances_to_ignore = get_activity_instances_to_ignore()

    process_name = args.get("prcfW", "all")
    session["process_name_workitemOverview"] = process_name

    prefix = "workitems.filter.process."
    perms = session.get("permissions", [])

    allowed_processes_set = set()
    for perm in perms:
        if perm.startswith(prefix):
            parts = perm.split(".")
            if len(parts) >= 2:
                allowed_processes_set.add(f"{parts[-2]}.{parts[-1]}")

    target_processes = []
    if process_name == "all":
        target_processes = list(allowed_processes_set)
    elif process_name in allowed_processes_set:
        target_processes = [process_name]

    params, process_placeholders, client_placeholders = prepare_process_selection_sql(
        prefix=prefix, process_name=process_name
    )

    docfields = args.getlist("docfield")
    docvalues = args.getlist("docvalue")

    where_clauses = [
        f"tp.Name IN ({process_placeholders})",
        f"tp.ClientName IN ({client_placeholders})",
        "twi.Status <> 2",
        f"tai.ActivityInstanceName not in ({activity_instances_to_ignore})",
    ]

    status_map = {"Ready": 0, "In Progress": 1, "Done": 5}
    if status and status in status_map:
        where_clauses.append("twi.Status = ?")
        params.append(status_map[status])

    if tag_filter and has_permission("workitems.filter.tag"):
        where_clauses.append(f"""
            EXISTS (
                SELECT 1
                FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                WHERE wt.workitemid = twi.id AND t.TagName like ?
            )
        """)
        params.append(f"%{tag_filter}%")

    if search_term and has_permission("workitems.filter.workitemid"):
        where_clauses.append("twi.id LIKE ?")
        params.append(f"%{search_term}%")

    if start_date and has_permission("workitems.filter.datetime"):
        where_clauses.append("twi.ModifiedAt >= ?")
        params.append(start_date)
    if end_date and has_permission("workitems.filter.datetime"):
        where_clauses.append("twi.ModifiedAt < ?")
        params.append(end_date)
    if priority and has_permission("workitems.filter.priority"):
        where_clauses.append("ISNULL(wim.Priority, 0) = ?")
        params.append(priority)
    if assigned_user and has_permission("workitems.filter.assignedUser"):
        if assigned_user == "None" or assigned_user == "Unassigned":
            where_clauses.append("(wim.AssignedUserID IS NULL)")
        else:
            where_clauses.append("wim.AssignedUserID = ?")
            params.append(assigned_user)

    extra_clauses = []
    extra_params = []
    _docfield_temp_tables = []  # [(temp_name, [ids])] for large ID sets

    if has_permission("workitems.filter.documentfields") and target_processes:
        valid_db_columns = get_valid_search_columns()

        conn_nex = None
        cursor_nex = None
        try:
            conn_nex = engine_nexora_db.raw_connection()
            cursor_nex = conn_nex.cursor()

            for docfield, docvalue in zip(docfields, docvalues, strict=False):
                docfield = (docfield or "").lower().strip()
                docvalue = (docvalue or "").strip()

                if not docvalue or not docfield:
                    continue

                target_config_col = f"col_{docfield}"
                if target_config_col not in valid_db_columns:
                    continue

                placeholders = ",".join(["?"] * len(target_processes))
                query = f"""
                    SELECT ProcessName, TableName, TableAlias, JoinCondition, TimeFilter, {target_config_col}
                    FROM SearchConfig
                    WHERE {target_config_col} IS NOT NULL
                    AND ProcessName IN ({placeholders})
                """
                configs = cursor_nex.execute(query, target_processes).fetchall()

                if not configs:
                    continue

                id_parts = []
                id_params = []
                for config in configs:
                    tbl = config.TableName
                    alias = config.TableAlias
                    db_column = getattr(config, target_config_col)
                    time_filter = config.TimeFilter
                    safe_col = f"CAST({alias}.{db_column} AS NVARCHAR(MAX))"

                    id_col = None
                    for part in re.split(r"\s*=\s*", (config.JoinCondition or "").strip()):
                        if re.match(rf"^{re.escape(alias)}\.\w+$", part.strip(), re.IGNORECASE):
                            id_col = part.strip()
                            break

                    if not id_col:
                        current_app.logger.warning(
                            f"Could not extract ID col from JoinCondition: {config.JoinCondition}"
                        )
                        continue

                    id_parts.append(f"""
                        SELECT DISTINCT {id_col} AS id
                        FROM {tbl} {alias}
                        WHERE {safe_col} COLLATE DATABASE_DEFAULT LIKE ?
                        AND {time_filter}
                    """)
                    id_params.append(f"%{docvalue}%")

                if not id_parts:
                    continue

                stat_conn = None
                try:
                    stat_conn = engine_statistics_db.raw_connection()
                    stat_cur = stat_conn.cursor()
                    union_sql = " UNION ALL ".join(id_parts)
                    stat_cur.execute(f"SELECT DISTINCT id FROM ({union_sql}) t", id_params)
                    matching_ids = [row[0] for row in stat_cur.fetchall()]
                except Exception as e:
                    current_app.logger.error(f"Error pre-fetching docfield IDs: {e}")
                    matching_ids = None
                finally:
                    if stat_conn:
                        stat_conn.close()

                if matching_ids is None:
                    continue
                if not matching_ids:
                    extra_clauses.append("1=0")
                elif len(matching_ids) > 500:
                    # Avoid SQL Server's 2100-param limit by using a temp table
                    temp_name = f"#docf{len(_docfield_temp_tables)}"
                    _docfield_temp_tables.append((temp_name, matching_ids))
                    extra_clauses.append(f"twi.ID IN (SELECT id FROM {temp_name})")
                else:
                    ph = ",".join(["?"] * len(matching_ids))
                    extra_clauses.append(f"twi.ID IN ({ph})")
                    extra_params.extend(matching_ids)

        except Exception as e:
            current_app.logger.error(f"Error in docfield pre-fetch block: {e}")
        finally:
            if cursor_nex:
                cursor_nex.close()
            if conn_nex:
                conn_nex.close()

    workitems_list = []
    total_items = 0
    conn = None
    cursor = None
    try:
        conn = engine_octo_db.raw_connection()
        cursor = conn.cursor()

        for temp_name, ids in _docfield_temp_tables:
            cursor.execute(f"CREATE TABLE {temp_name} (id NVARCHAR(255))")
            for i in range(0, len(ids), 1000):
                batch = ids[i : i + 1000]
                cursor.execute(
                    f"INSERT INTO {temp_name}(id) VALUES {','.join(['(?)'] * len(batch))}",
                    batch,
                )

        full_where = " AND ".join(where_clauses + extra_clauses)
        full_params = list(params) + extra_params

        # count pass
        cursor.execute(
            f"""
            SELECT COUNT(twi.ID)
            FROM t_WorkItems twi
            INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
            INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
            LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.workitemid
            WHERE {full_where}
        """,
            full_params,
        )
        total_items = cursor.fetchone()[0] or 0

        # data pass
        cursor.execute(
            f"""
            WITH WorkitemCTE AS (
                SELECT
                    twi.ModifiedAt, twi.ID AS WorkItemID,
                    CASE
                        WHEN twi.Status = 0 THEN 'Ready' WHEN twi.Status = 5 THEN 'Done' ELSE 'In Progress'
                    END AS Status,
                    CASE
                        WHEN twi.Status = 5 THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'Validation'
                        WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'Import'
                        WHEN tai.ActivityInstanceName LIKE '%Extract%' OR tai.ActivityInstanceName LIKE '%OCR%' THEN 'Extraction'
                        WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' or tai.ActivityInstanceName like '%Lieferung%' THEN 'Delivery'
                        ELSE 'Extraction'
                    END AS CurrentStage,
                    wim.Priority,
                    (
                        SELECT t.TagID AS id, t.TagName AS name, t.TagColor AS color
                        FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                        JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.WorkItemID = twi.ID
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.WorkItemID
                WHERE {full_where}
            )
            SELECT ModifiedAt, WorkItemID, Status, CurrentStage, Priority, TagsJSON
            FROM WorkitemCTE WHERE rn = 1
            ORDER BY ModifiedAt DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """,
            [*full_params, offset, per_page],
        )
        for row in cursor.fetchall():
            workitems_list.append(
                {
                    "modifiedat": row.ModifiedAt,
                    "workitemid": row.WorkItemID,
                    "status": row.Status,
                    "current_stage": row.CurrentStage,
                    "priority": row.Priority or 0,
                    "tags": json.loads(row.TagsJSON) if row.TagsJSON else [],
                }
            )

    except Exception as e:
        current_app.logger.error(f"Database error in _get_workitems_data: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_pages = math.ceil(total_items / per_page)
    return {
        "workitems": workitems_list,
        "pagination": {
            "currentPage": page,
            "totalPages": total_pages,
            "totalItems": total_items,
            "perPage": per_page,
        },
    }


# ---------------------------- routes ---------------------------- #


@require_permission("workitems.filter.documentfields")
def api_docfield_values():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    process = request.args.get("process", "all")
    field = (request.args.get("field", "") or "").lower().strip()
    q = (request.args.get("q", "") or "").strip()
    if not field:
        return jsonify([])

    target_col_name = f"col_{field}"
    conn = None
    cur = None
    try:
        conn = engine_nexora_db.raw_connection()
        cur = conn.cursor()

        query = f"SELECT * FROM SearchConfig WHERE {target_col_name} IS NOT NULL"
        db_params = []
        if process != "all":
            query += " AND ProcessName = ?"
            db_params.append(process)

        configs = cur.execute(query, db_params).fetchall()

        if not configs:
            return jsonify([])

        cache_key = f"docfield_vals_{process}_{field}"
        all_vals = cache.get(cache_key)

        if all_vals is None:
            parts = []
            for config in configs:
                tbl = config.TableName
                col_name = getattr(config, target_col_name)
                time_filter = config.SuggestionTimeFilter
                safe_col = f"CAST({col_name} AS NVARCHAR(MAX))"
                parts.append(f"""
                    SELECT {safe_col} COLLATE DATABASE_DEFAULT AS Val
                    FROM [{DB_STATISTICS}].{tbl}
                    WHERE {col_name} IS NOT NULL
                      AND {safe_col} <> ''
                      AND {time_filter}
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
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


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

    ids_param = request.args.get("ids", "").strip()
    specific_ids = (
        set(int(i) for i in ids_param.split(",") if i.strip().isdigit()) if ids_param else set()
    )

    try:
        result = _get_workitems_data(request.args, export_all=True)
        workitems = result.get("workitems", [])
    except Exception as e:
        current_app.logger.error(f"Export: failed to fetch workitems: {e}")
        return jsonify({"error": "Failed to fetch workitems"}), 500

    if specific_ids:
        workitems = [w for w in workitems if w["workitemid"] in specific_ids]

    if not workitems:
        output = io.StringIO()
        output.write("No workitems to export\r\n")
        resp = make_response(output.getvalue())
        resp.headers["Content-Type"] = "text/csv; charset=utf-8"
        resp.headers["Content-Disposition"] = "attachment; filename=workitems_export.csv"
        return resp

    domains = {}
    for w in workitems:
        wid = w["workitemid"]
        try:
            domains[wid] = get_domain_for_workitem(wid)
        except Exception:
            domains[wid] = OCTO_DOMAIN

    _include_fields = include_fields
    _include_history = include_history
    _include_images = include_images
    _app = current_app._get_current_object()

    def _fetch(wid):
        detail = {"fields": {}, "history": [], "images": []}
        domain = domains.get(wid, OCTO_DOMAIN)
        with _app.app_context():
            if _include_fields or _include_images:
                try:
                    urls, extensions = [], []
                    cached = cache.get(f"media_info_{wid}")
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
                            cache.set(
                                f"media_info_{wid}", {"fields": fields, "media_count": len(urls)}
                            )
                            if urls:
                                cache.set(
                                    f"media_data_{wid}", {"extensions": extensions, "urls": urls}
                                )
                    if _include_images:
                        cached_media = cache.get(f"media_data_{wid}")
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
                    cached = cache.get(f"audithistory_{wid}")
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
                        cache.set(f"audithistory_{wid}", history_list, timeout=1800)
                        detail["history"] = history_list
                except Exception as e:
                    _app.logger.error(f"Export: history error for {wid}: {e}")
        return wid, detail

    details_map = {}
    if include_fields or include_history or include_images:
        max_workers = min(10, len(workitems))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch, w["workitemid"]): w["workitemid"] for w in workitems}
            for future in as_completed(futures, timeout=120):
                try:
                    wid, detail = future.result()
                    details_map[wid] = detail
                except Exception as e:
                    wid = futures[future]
                    _app.logger.error(f"Export: future error for {wid}: {e}")
                    details_map[wid] = {"fields": {}, "history": [], "images": []}

    all_field_keys = []
    if include_fields:
        seen_keys = set()
        for w in workitems:
            for k in details_map.get(w["workitemid"], {}).get("fields", {}):
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_field_keys.append(k)

    max_images = 0
    if include_images:
        for w in workitems:
            max_images = max(
                max_images, len(details_map.get(w["workitemid"], {}).get("images", []))
            )

    priority_label = {3: "High", 2: "Medium", 1: "Low"}
    headers = ["Workitem ID", "Status", "Stage", "Last Movement At", "Priority", "Tags"]
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
        detail = details_map.get(wid, {"fields": {}, "history": [], "images": []})
        ts = w.get("modifiedat")
        date_str = (
            ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts or "")[:19]
        )

        row = [
            wid,
            w.get("status", ""),
            w.get("current_stage", ""),
            date_str,
            priority_label.get(w.get("priority", 0), ""),
            "; ".join(t["name"] for t in (w.get("tags") or [])),
        ]
        if include_fields:
            fields = detail["fields"]
            row.extend(fields.get(k, "") for k in all_field_keys)
        if include_history:
            history = sorted(
                detail.get("history", []), key=lambda h: h.get("Step", 0), reverse=True
            )
            row.append(
                "; ".join(f"Step {h['Step']}: {h['Activity']} @ {h['DateTime']}" for h in history)
            )
        if include_images:
            images = detail.get("images", [])
            row.extend(images[i] if i < len(images) else "" for i in range(max_images))
        writer.writerow(row)

    csv_content = output.getvalue()
    response = make_response(csv_content)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
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

        tag_filter_perm = has_permission("workitems.filter.tag")
        tag_filter = request.args.get("tag", "").strip() if tag_filter_perm else None

        datetime_perm = has_permission("workitems.filter.datetime")
        start_date_str = request.args.get("startDate", "") if datetime_perm else None
        end_date_str = request.args.get("endDate", "") if datetime_perm else None
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else None

        priority_perm = has_permission("workitems.filter.priority")
        priority = request.args.get("priority", "") if priority_perm else None

        assigned_user_perm = has_permission("workitems.filter.assignedUser")
        assigned_user = request.args.get("assignedUser", "") if assigned_user_perm else None

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

        details_view_perm = has_permission("workitems.details.view")
        details_images_perm = has_permission("workitems.details.view.images")
        details_audit_perm = has_permission("workitems.details.view.audit")
        details_fields_perm = has_permission("workitems.details.view.fields")

        details_set_priority_perm = has_permission("workitems.details.set.priority")
        details_add_tag_perm = has_permission("workitems.details.add.tag")
        details_assign_users_perm = has_permission("workitems.details.assign.users")
        details_add_comment_perm = has_permission("workitems.details.add.comment")

        portal_assigned_users_filter = get_all_portal_users("workitems", "filter.assignedUser")
        return render_template(
            "workitems_overview.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            search=search_term,
            status=status,
            tag=tag_filter,
            startDate=start_date,
            endDate=end_date,
            priority=priority,
            assignedUser=assigned_user,
            portal_assignedUsers_filter=portal_assigned_users_filter,
            docfield=docfields[0] if docfields else "",
            docvalue=docvalues[0] if docvalues else "",
            pageV=page_visibility(),
            allowed_processes=allowed_processes,
            search_term_perm=search_term_perm,
            status_perm=status_perm,
            tag_filter_perm=tag_filter_perm,
            datetime_perm=datetime_perm,
            priority_perm=priority_perm,
            assigned_user_perm=assigned_user_perm,
            doc_fields_values_perm=doc_fields_values_perm,
            details_view_perm=details_view_perm,
            details_images_perm=details_images_perm,
            details_audit_perm=details_audit_perm,
            details_fields_perm=details_fields_perm,
            details_set_priority_perm=details_set_priority_perm,
            details_add_tag_perm=details_add_tag_perm,
            details_assign_users_perm=details_assign_users_perm,
            details_add_comment_perm=details_add_comment_perm,
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


def get_single_workitem(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    cursor = None
    try:
        conn = engine_octo_db.raw_connection()
        cursor = conn.cursor()

        query = f"""
            WITH WorkitemCTE AS (
                SELECT
                    twi.ID AS WorkItemID,
                    (
                        SELECT
                            t.TagID AS id,
                            t.TagName AS name,
                            t.TagColor AS color
                        FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                        JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.WorkItemID = twi.ID
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                WHERE twi.ID = ?
            )
            SELECT WorkItemID, TagsJSON
            FROM WorkitemCTE
            WHERE rn = 1
        """
        cursor.execute(query, workitemid)
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Workitem not found"}), 404

        workitem_data = {
            "workitemid": row.WorkItemID,
            "tags": json.loads(row.TagsJSON) if row.TagsJSON else [],
        }
        return jsonify(workitem_data)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch single workitem {workitemid}: {e}")
        return jsonify({"error": _("Could not fetch workitem data")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def api_get_media_info(workitem_id):
    if not has_permission("workitems.details.view"):
        return jsonify({"error": _("Not authorized")}), 403
    try:
        can_view_images = has_permission("workitems.details.view.images")
        can_view_fields = has_permission("workitems.details.view.fields")

        def _suppress(data):
            # Highlighting needs BOTH perms: fields to see the values, images to
            # see WHERE (boxes are drawn over the page image). Returns a copy so
            # the cached object is never mutated.
            d = data.copy()
            if not can_view_images:
                d["media_count"] = 0
            if not can_view_fields:
                d["fields"] = {}
                d["field_sources"] = []
                d["table_sources"] = []
            elif not can_view_images:
                d["field_sources"] = [{**s, "locations": []} for s in d.get("field_sources", [])]
                d["table_sources"] = [
                    {
                        **t,
                        "rows": [
                            [{**c, "locations": []} for c in row] for row in t.get("rows", [])
                        ],
                    }
                    for t in d.get("table_sources", [])
                ]
            return d

        cached_info = cache.get(f"media_info_{workitem_id}")
        if cached_info:
            return jsonify(_suppress(cached_info))

        domain = get_domain_for_workitem(workitem_id)
        returndata = get_workitemdata_param(workitem_id, domain)
        if not returndata:
            return jsonify({"error": _("Workitem not found")}), 404

        workitemdata, document_id = returndata
        extensions, urls, fields, field_sources, table_sources = get_extensions_urls_fields(
            workitemdata, document_id, domain, with_tables=True
        )

        media_count = len(urls) if urls else 0

        if media_count > 0:
            cache.set(f"media_data_{workitem_id}", {"extensions": extensions, "urls": urls})

        response_data = {
            "workitem_id": workitem_id,
            "media_count": media_count,
            "fields": fields,
            "field_sources": field_sources,
            "table_sources": table_sources,
        }

        cache.set(f"media_info_{workitem_id}", response_data)

        return jsonify(_suppress(response_data))
    except Exception as e:
        print(f"An error occurred in get_media_info: {e}")
        return jsonify({"error": _("Internal Server Error")}), 500


@require_permission("workitems.details.view.images")
def api_get_media_raw(workitem_id, media_index):
    try:
        domain = get_domain_for_workitem(workitem_id)
        media_data = cache.get(f"media_data_{workitem_id}")
        if not media_data:
            returndata = get_workitemdata_param(workitem_id, domain)
            if not returndata:
                return Response(_("Workitem not found"), status=404)

            workitemdata, document_id = returndata
            extensions, urls, fields, _fs, _ts = get_extensions_urls_fields(
                workitemdata, document_id, domain
            )
            media_data = {"extensions": extensions, "urls": urls}
            cache.set(f"media_data_{workitem_id}", media_data)

        extensions = media_data.get("extensions", [])
        urls = media_data.get("urls", [])

        if media_index >= len(urls):
            return Response(_("Media index out of bounds"), status=404)

        target_url = urls[media_index]
        target_extension = extensions[media_index].lower()

        if target_extension == ".tif":
            _tif_cache_key = f"media_raw_tif_{workitem_id}_{media_index}"
            cached_jpeg = cache.get(_tif_cache_key)
            if cached_jpeg is not None:
                return send_file(
                    io.BytesIO(cached_jpeg), mimetype="image/jpeg", as_attachment=False
                )

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
                    return send_file(
                        io.BytesIO(jpeg_bytes), mimetype="image/jpeg", as_attachment=False
                    )
            except Exception as e:
                print(f"An error occurred during TIFF conversion: {e}")
                return _("Failed to process TIFF image"), 500

        raw_media_bytes = get_media(target_url, domain)
        if target_extension == ".jpg":
            mimetype = "image/jpeg"
        elif target_extension == ".png":
            mimetype = "image/png"
        else:
            mimetype = "application/octet-stream"

        response = make_response(raw_media_bytes)
        response.headers.set("Content-Type", mimetype)
        response.headers.set("Cache-Control", "private, max-age=3600")
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return Response(_("Internal Server Error"), status=500)


@require_permission("workitems.details.view.audit")
def get_audithistory(workitem_id):
    _cache_key = f"audithistory_{workitem_id}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        domain = get_domain_for_workitem(workitem_id)
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

        complete_array = []
        total_steps = len(unique_activities)

        for i, (activity_id, time_stamp) in enumerate(unique_activities.items()):
            activity_name = get_activity_type_name(activity_id, domain)

            step_info = {
                "Activity": activity_name,
                "DateTime": time_stamp,
                "Step": total_steps - i,
            }
            complete_array.append(step_info)

        cache.set(_cache_key, complete_array, timeout=1800)
        return jsonify(complete_array)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"{_('Failed to fetch audit history')}: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"{_('An unexpected error occurred')}: {e}"}), 500


# ---------------------------- collaboration apis ---------------------------- #


def get_users_for_mentions():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    _all_users = has_permission("admin.interact.users.all")
    _org = session.get("organizationcode", "")
    _cache_key = f"users_mentions_{'all' if _all_users else _org}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        if has_permission("workitems.details.add.comment"):
            if _all_users:
                cursor.execute("SELECT userID, username, fullname FROM Users")
            else:
                cursor.execute(
                    """
                    SELECT userID, username, fullname FROM Users
                    WHERE organizationcode IN ('SYDC', ?) AND accessid not in (1,2)
                    """,
                    _org,
                )
        users = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        cache.set(_cache_key, users, timeout=900)
        return jsonify(users)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch users for mentions: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_workitem_interactions(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    _cache_key = f"interactions_{workitemid}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        sql_query = """
            SELECT c.CommentText, c.Timestamp, u.username, u.userID
            FROM Workitem_Comments c
            JOIN Users u ON c.UserID = u.userID
            WHERE c.WorkItemID = ?
            ORDER BY c.Timestamp ASC
        """
        cursor.execute(sql_query, [workitemid])
        comments_data = cursor.fetchall()

        cursor.execute(
            """
            SELECT t.TagID, t.TagName, t.TagColor
            FROM Workitem_Tags wt
            JOIN Tags t ON wt.TagID = t.TagID
            WHERE wt.workitemid = ?
            """,
            (workitemid,),
        )
        tags_data = cursor.fetchall()

        cursor.execute(
            "SELECT Priority, AssignedUserID FROM Workitem_Metadata WHERE WorkItemID = ?",
            (workitemid,),
        )
        meta_row = cursor.fetchone()

        if meta_row is None and not comments_data and not tags_data:
            return jsonify(
                {
                    "priority": 0,
                    "assigneduserid": "None",
                    "comments": [],
                    "tags": [],
                    "message": _("No data found for this workitem."),
                }
            ), 200

        priority = meta_row[0] if (meta_row and meta_row[0] is not None) else 0
        assigneduserid = meta_row[1] if (meta_row and meta_row[1] is not None) else "None"
        tags = (
            [{"id": trow.TagID, "name": trow.TagName, "color": trow.TagColor} for trow in tags_data]
            if tags_data
            else []
        )

        comments = []
        if comments_data:
            for crow in comments_data:
                comments.append(
                    {
                        "CommentText": crow.CommentText,
                        "Timestamp": crow.Timestamp.isoformat(),
                        "username": crow.username,
                        "userID": crow.userID,
                        "userIcon": resolve_user_icon_url(crow.userID),
                    }
                )
        result = {
            "priority": priority,
            "assigneduserid": assigneduserid,
            "comments": comments,
            "tags": tags,
        }
        cache.set(_cache_key, result, timeout=600)
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch interactions for workitem {workitemid}: {e}")
        return jsonify({"error": _("Could not fetch interactions")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def add_workitem_comment(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    comment_text = data.get("commentText")
    if not comment_text:
        return jsonify({"success": False, "message": _("Comment cannot be empty.")}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO Workitem_Comments (WorkItemID, UserID, CommentText)
            VALUES (?, ?, ?)
            """,
            (workitemid, session["userid"], comment_text),
        )
        conn.commit()

        cursor.execute("SELECT TOP 1 CommentID FROM Workitem_Comments ORDER BY CommentID DESC")
        comment_id = cursor.fetchone()[0]

        mentions = re.findall(r"@(\w+\.\w+)", comment_text)
        if mentions:
            placeholders = ",".join("?" for _m in mentions)
            cursor.execute(
                f"SELECT userID, username FROM Users WHERE username IN ({placeholders})",
                mentions,
            )
            mentioned_users = cursor.fetchall()
            for user in mentioned_users:
                cursor.execute(
                    "INSERT INTO Comment_Mentions (CommentID, MentionedUserID) VALUES (?, ?)",
                    (comment_id, user.userID),
                )
                notification_link = url_for(
                    "workitems_overview", search=workitemid, _external=False
                )
                create_notification(
                    user.userID,
                    f"{session['username']} mentioned you on workitem {workitemid}",
                    link=notification_link,
                    icon="fa-at",
                )
        conn.commit()
        cache.delete(f"interactions_{workitemid}")
        return jsonify({"success": True, "message": _("Comment added.")})
    except Exception as e:
        current_app.logger.error(f"Error adding comment for workitem {workitemid}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def assign_workitem(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    assigned_user_id = data.get("assignedUserID")
    if assigned_user_id is None:
        return jsonify({"success": False, "message": _("Invalid assignment.")}), 400
    elif assigned_user_id == "None":
        assigned_user_id = None
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETDATE())) AS source (WorkItemID, AssignedUserID, UserID, UpdateTime)
            ON target.WorkItemID = source.WorkItemID
            WHEN MATCHED THEN
                UPDATE SET AssignedUserID = source.AssignedUserID, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (WorkItemID, AssignedUserID, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.WorkItemID, source.AssignedUserID, source.UserID, source.UpdateTime);
            """,
            (workitemid, assigned_user_id, session["userid"]),
        )

        conn.commit()
        cache.delete(f"interactions_{workitemid}")
        if assigned_user_id is not None and assigned_user_id != session["userid"]:
            notification_link = url_for("workitems_overview", search=workitemid, _external=False)
            create_notification(
                assigned_user_id,
                f"{session['username']} {_('assigned you on workitem')} {workitemid}",
                link=notification_link,
                icon="fa-people-carry-box",
            )
        return jsonify({"success": True, "message": _("Assignment updated.")})
    except Exception as e:
        current_app.logger.error(f"Error setting assignment for workitem {workitemid}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def set_workitem_priority(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    priority = data.get("priority")
    if priority is None or priority not in [0, 1, 2, 3]:
        return jsonify({"success": False, "message": _("Invalid priority level.")}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETDATE())) AS source (WorkItemID, Priority, UserID, UpdateTime)
            ON target.WorkItemID = source.WorkItemID
            WHEN MATCHED THEN
                UPDATE SET Priority = source.Priority, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (WorkItemID, Priority, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.WorkItemID, source.Priority, source.UserID, source.UpdateTime);
            """,
            (workitemid, priority, session["userid"]),
        )

        conn.commit()
        cache.delete(f"interactions_{workitemid}")
        return jsonify({"success": True, "message": _("Priority updated.")})
    except Exception as e:
        current_app.logger.error(f"Error setting priority for workitem {workitemid}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_all_tags():
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    cached = cache.get("all_tags")
    if cached is not None:
        return jsonify(cached)

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
        tags = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        cache.set("all_tags", tags, timeout=1800)
        return jsonify(tags)
    except Exception as e:
        current_app.logger.error(f"Failed to fetch all tags: {e}")
        return jsonify({"error": _("Could not fetch tags")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def api_workitems_page_init():
    if "username" not in session:
        return jsonify({}), 401

    # Tags
    tags = cache.get("all_tags")
    if tags is None:
        conn = None
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
            tags = [
                dict(zip([column[0] for column in cursor.description], row, strict=False))
                for row in cursor.fetchall()
            ]
            cache.set("all_tags", tags, timeout=1800)
        except Exception as e:
            current_app.logger.error(f"page_init: failed to fetch tags: {e}")
            tags = []
        finally:
            if conn:
                conn.close()

    # Users
    _all_users = has_permission("admin.interact.users.all")
    _org = session.get("organizationcode", "")
    _users_key = f"users_mentions_{'all' if _all_users else _org}"
    users = cache.get(_users_key)
    if users is None:
        conn = None
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            if has_permission("workitems.details.add.comment"):
                if _all_users:
                    cursor.execute("SELECT userID, username, fullname FROM Users")
                else:
                    cursor.execute(
                        """
                        SELECT userID, username, fullname FROM Users
                        WHERE organizationcode IN ('SYDC', ?) AND accessid not in (1,2)
                        """,
                        _org,
                    )
                users = [
                    dict(zip([column[0] for column in cursor.description], row, strict=False))
                    for row in cursor.fetchall()
                ]
            else:
                users = []
            cache.set(_users_key, users, timeout=900)
        except Exception as e:
            current_app.logger.error(f"page_init: failed to fetch users: {e}")
            users = []
        finally:
            if conn:
                conn.close()

    perms = session.get("permissions", [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split(".")[-2] + "." + perm.split(".")[-1])
        for perm in perms
        if perm.startswith(prefix)
    }
    current_lang = str(get_locale())
    _fields_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}"
    field_config = cache.get(_fields_key)
    if field_config is None:
        lang_column_map = {
            "de": "GermanLabel",
            "fr": "FrenchLabel",
            "it": "ItalianLabel",
            "en": "EnglishLabel",
        }
        target_column = lang_column_map.get(current_lang, "EnglishLabel")
        search_options = {}
        db_labels_map = {}
        conn = None
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels"
                )
                for row in cursor.fetchall():
                    translated_label = getattr(row, target_column) or row.EnglishLabel
                    db_labels_map[row.FieldKey] = translated_label
            except Exception:
                pass
            cursor.execute("SELECT TOP 0 * FROM SearchConfig")
            cols = [c[0] for c in cursor.description if c[0].startswith("col_")]
            query = f"SELECT ProcessName, {','.join(cols)} FROM SearchConfig"
            cursor.execute(query)
            for row in cursor.fetchall():
                proc_name = row.ProcessName
                if proc_name not in allowed_processes:
                    continue
                fields = []
                for i, col_name in enumerate(cols):
                    if row[i + 1]:
                        field_key = col_name.replace("col_", "")
                        nice_label = db_labels_map.get(
                            field_key, field_key.replace("_", " ").title()
                        )
                        fields.append({"value": field_key, "label": nice_label})
                fields.sort(key=lambda x: x["label"])
                search_options[proc_name] = fields
        except Exception as e:
            current_app.logger.error(f"page_init: failed to fetch field config: {e}")
        finally:
            if conn:
                conn.close()
        field_config = {"search_options": search_options, "labels": db_labels_map}
        cache.set(_fields_key, field_config, timeout=3600)

    return jsonify({"tags": tags, "users": users, "field_config": field_config})


def add_tag_to_workitem(workitemid):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    tag_name = data.get("tagName", "").strip()
    tag_color = data.get("tagColor", "#6B7280")

    if not tag_name:
        return jsonify({"success": False, "message": _("Tag name cannot be empty.")}), 400

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT TagID FROM Tags WHERE TagName = ?", (tag_name,))
        tag = cursor.fetchone()

        if tag:
            tag_id = tag.TagID
        else:
            cursor.execute(
                "INSERT INTO Tags (TagName, TagColor, CreatedByUserID) OUTPUT INSERTED.TagID VALUES (?, ?, ?)",
                (tag_name, tag_color, session["userid"]),
            )
            tag_id = cursor.fetchone().TagID

        cursor.execute(
            "SELECT 1 FROM Workitem_Tags WHERE WorkItemID = ? AND TagID = ?", (workitemid, tag_id)
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": _("Workitem already has this tag.")}), 409

        cursor.execute(
            "INSERT INTO Workitem_Tags (WorkItemID, TagID) VALUES (?, ?)", (workitemid, tag_id)
        )
        conn.commit()
        cache.delete(f"interactions_{workitemid}")
        cache.delete("all_tags")

        return jsonify(
            {
                "success": True,
                "message": _("Tag added successfully."),
                "tag": {"TagID": tag_id, "TagName": tag_name, "TagColor": tag_color},
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error adding tag to workitem {workitemid}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def remove_tag_from_workitem(workitemid, tag_id):
    if "username" not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM Workitem_Tags WHERE WorkItemID = ? AND TagID = ?",
            (workitemid, tag_id),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": _("Tag association not found.")}), 404

        cache.delete(f"interactions_{workitemid}")
        cache.delete("all_tags")
        return jsonify({"success": True, "message": _("Tag removed successfully.")})
    except Exception as e:
        current_app.logger.error(f"Error removing tag {tag_id} from workitem {workitemid}: {e}")
        return jsonify({"success": False, "message": _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
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
        "/api/workitem/<int:workitemid>",
        endpoint="get_single_workitem",
        view_func=get_single_workitem,
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
        "/api/users", endpoint="get_users_for_mentions", view_func=get_users_for_mentions
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/interactions",
        endpoint="get_workitem_interactions",
        view_func=get_workitem_interactions,
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/comment",
        endpoint="add_workitem_comment",
        view_func=add_workitem_comment,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/assign",
        endpoint="assign_workitem",
        view_func=assign_workitem,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/priority",
        endpoint="set_workitem_priority",
        view_func=set_workitem_priority,
        methods=["POST"],
    )
    app.add_url_rule("/api/tags", endpoint="get_all_tags", view_func=get_all_tags)
    app.add_url_rule(
        "/api/workitems_page_init",
        endpoint="api_workitems_page_init",
        view_func=api_workitems_page_init,
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/tags",
        endpoint="add_tag_to_workitem",
        view_func=add_tag_to_workitem,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/workitem/<int:workitemid>/tags/<int:tag_id>",
        endpoint="remove_tag_from_workitem",
        view_func=remove_tag_from_workitem,
        methods=["DELETE"],
    )
