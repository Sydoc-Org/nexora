"""Descriptor-driven factory for the repeated Generali per-table endpoints.

Five Generali tables (AttendanceEntries, BaseServiceEntries, ProjectEntries,
QualityCheckEntries, IssReports) grew near-identical copies of the same eight
endpoint families:
``monthreport``, ``api_org_users``, ``api_organizations``, ``api_filter_users``,
``api_list`` and ``api_add`` / ``api_edit`` / ``api_delete``. This module holds
one implementation of each, generated from a :class:`CrudTable` descriptor that
carries the *genuine* per-table differences (table name, permission prefix,
columns, validators, category sets, log labels).

Contract (beautify-phase-0-1, Task 14):

* Generated views are bound in the owning submodule under their ORIGINAL
  function name and re-exported from ``__init__`` unchanged, so ``gv.<fn>`` and
  every endpoint/URL stay byte-identical. No Blueprints, no endpoint renames.
* A table only uses the families that actually fit it. Where a table genuinely
  diverges (Reporting's ``api_add`` duplicate check, its body-``id`` ``api_edit``)
  the hand-written view stays in the submodule — the descriptor never
  force-uniforms real differences.
* Every generated view that touches a DB engine re-imports it from the package
  (``from . import engine_generali_db``) at call time, so tests that
  ``monkeypatch.setattr(gv, "engine_generali_db", ...)`` keep working across the
  package boundary (same reason as the hand-written views that do this).
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from flask import current_app, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext as _

from ...security import (
    PermissionDenied,
    _check_add_deadline,
    _check_generali_record_org,
    has_permission,
    page_visibility,
    require_any_permission,
    require_permission,
)
from ._scope import _generali_orgs_for_userids, _generali_scope_where

# Sentinel marking, inside CrudList.filters, where the grant-derived scope
# clauses are spliced in. Position matters: it fixes the SQL parameter order.
SCOPE = "__scope__"

# Export ceiling for ?all=true on the generated api_list endpoints (beautify
# phase-2c Task 5 / D4): non-breaking below the cap -- a caller with <= this
# many matching rows gets identical behaviour to before. Only the pathological
# case (e.g. an unfiltered export against a multi-million-row table) is capped
# instead of returning every row.
ALL_EXPORT_CAP = 100_000


# --------------------------------------------------------------------------- #
# Descriptor pieces
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Filter:
    """One optional query-string filter on a list endpoint.

    op:
      ``gte`` / ``lte`` / ``eq``  -- ``request.args.get(param, "").strip()``,
                                    skipped when empty.
      ``eq_in_set``               -- as ``eq``, but only applied when the value
                                    is a member of ``allowed``.
      ``eq_or_null``              -- ``request.args.get(param)``; absent = not
                                    filtered, ``""`` = ``IS NULL``.
      ``bool``                    -- ``"true"``/``"false"`` mapped to 1/0.
    """

    param: str
    column: str
    op: str = "eq"
    allowed: Collection[Any] | None = None


@dataclass(frozen=True)
class Field:
    """One writable column on the add/edit endpoints.

    kind:
      ``str``        -- ``body.get(json, "").strip()``
      ``opt_str``    -- ``raw.strip() if raw else None``
      ``blank_null`` -- ``body.get(json, "")``; ``""`` stored as NULL (unstripped)
      ``float``      -- coerced, must be > ``minimum`` (exclusive)
      ``int``        -- coerced, must be >= ``minimum`` (inclusive)
      ``const``      -- fixed ``const`` value, never read from the body
    """

    column: str
    json: str | None = None
    kind: str = "str"
    required: bool = False
    allowed: Collection[Any] | None = None
    minimum: float | None = None
    error: str | None = None
    const: Any = None


@dataclass(frozen=True)
class CrudList:
    """Shape of one ``api_list`` endpoint."""

    select: str
    order_by: str
    filters: tuple
    record: Callable[[tuple, dict], dict]
    user_index: int
    # (sql, response_key, converter) for the extra aggregate column, or None
    aggregate: tuple | None = None


@dataclass(frozen=True)
class CrudMonthReport:
    """Shape of one ``monthreport`` page.

    ``group_column`` set -> grouped query, ``row_builder`` maps each raw row and
    ``summary`` receives the built row list. ``group_column`` None -> a single
    aggregate row, ``rows`` renders empty and ``summary`` receives the raw row.
    """

    section: str
    section_title: str
    back_endpoint: str
    date_column: str
    measures: str
    summary: Callable[[Any], dict]
    group_column: str | None = None
    row_builder: Callable[[tuple], dict] | None = None
    self_restrict: bool = True


@dataclass(frozen=True)
class CrudWrite:
    """Shape of the ``api_add`` / ``api_edit`` pair."""

    fields: tuple
    date_json: str
    insert_order: tuple
    update_order: tuple


@dataclass
class CrudTable:
    """Everything the factory needs for one Generali table."""

    slug: str  # api path + endpoint-name segment, e.g. "baseservices"
    table: str  # fully bracketed SQL table name
    user_column: str  # owner column, e.g. "UserID"
    perm_prefix: str  # permission prefix, e.g. "tenant.generali.baseservices"
    api_base: str  # e.g. "/api/generali/baseservices"
    label: str  # log label, e.g. "Generali Base Services"
    user_lookup_label: str = ""  # label in the list endpoint's warning log
    filter_users_label: str = ""  # log label override (historically compressed)
    monthreport_label: str = ""  # log label override for the month report
    monthreport_url: str = ""
    monthreport_endpoint: str = ""
    monthreport: CrudMonthReport | None = None
    list_spec: CrudList | None = None
    write: CrudWrite | None = None
    has_org_users: bool = True
    has_delete: bool = True
    organizations: bool = True  # generate api_organizations
    organizations_restrict: bool = True  # ...with the own-records restriction
    filter_users: bool = True
    views: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        self.user_lookup_label = self.user_lookup_label or self.label
        self.filter_users_label = self.filter_users_label or self.label
        self.monthreport_label = self.monthreport_label or self.label
        self.views = _build_views(self)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _fail():
    return jsonify({"success": False, "error": _("An unexpected error occurred")}), 500


def _lookup_users(user_ids, label):
    """{userid: {"fullname", "orgCode"}} for the list endpoints' row enrichment.

    Never fatal: a failed lookup degrades to unnamed rows, as before.
    """
    user_map: dict = {}
    if not user_ids:
        return user_map
    from . import engine_nexora_db

    try:
        nx_conn = engine_nexora_db.raw_connection()
        nx_cur = nx_conn.cursor()
        placeholders = ",".join(["?"] * len(user_ids))
        nx_cur.execute(
            f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
            user_ids,
        )
        for uid, fullname, orgcode in nx_cur.fetchall():
            user_map[uid] = {"fullname": fullname, "orgCode": orgcode}
        nx_cur.close()
        nx_conn.close()
    except Exception as ue:
        current_app.logger.warning(f"User lookup failed for {label}: {ue}")
    return user_map


def _month_window():
    """Clamped (year, month) from the query string plus the derived nav context."""
    today = date.today()
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month
    month = max(1, min(12, month))
    year = max(2000, min(today.year, year))

    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    return {
        "year": year,
        "month": month,
        "month_label": first_day.strftime("%B %Y"),
        "prev_month": month - 1 if month > 1 else 12,
        "prev_year": year if month > 1 else year - 1,
        "next_month": month + 1 if month < 12 else 1,
        "next_year": year if month < 12 else year + 1,
        "is_current_month": year == today.year and month == today.month,
        "first_day": first_day,
        "last_day": last_day,
    }


def _parse_write_body(d, body):
    """(values_by_column, error_response) for an add/edit request body.

    Validation order matches the hand-written views it replaces: required
    fields first (one shared "Missing required fields"), then allowed-value
    sets, then numeric coercion.
    """
    raw = {}
    for f in d.write.fields:
        if f.kind == "const":
            raw[f.column] = f.const
        elif f.kind == "str":
            raw[f.column] = body.get(f.json, "").strip()
        elif f.kind == "opt_str":
            value = body.get(f.json)
            raw[f.column] = value.strip() if value else None
        elif f.kind == "blank_null":
            value = body.get(f.json, "")
            raw[f.column] = value if value != "" else None
        else:  # float / int -- coerced below, kept raw for the required check
            raw[f.column] = body.get(f.json)

    for f in d.write.fields:
        if not f.required:
            continue
        value = raw[f.column]
        missing = value is None if f.kind in ("float", "int") else not value
        if missing:
            return None, (jsonify({"success": False, "error": "Missing required fields"}), 400)

    for f in d.write.fields:
        if f.allowed is not None and raw[f.column] not in f.allowed:
            return None, (jsonify({"success": False, "error": f.error}), 400)

    for f in d.write.fields:
        if f.kind not in ("float", "int"):
            continue
        try:
            value = float(raw[f.column]) if f.kind == "float" else int(raw[f.column])
            if f.kind == "float" and value <= f.minimum:
                raise ValueError
            if f.kind == "int" and value < f.minimum:
                raise ValueError
        except (TypeError, ValueError):
            return None, (jsonify({"success": False, "error": f.error}), 400)
        raw[f.column] = value

    return raw, None


def _resolve_target_user(d, body):
    """(user_id, error_response) -- who the new record is booked for.

    Defaults to the caller. Booking for someone else needs the ``.org`` or
    ``.all`` add grant, and without the latter the target must sit in the
    caller's own org.
    """
    caller_id = session.get("userid")
    target_raw = body.get("userId")
    if target_raw is None or str(target_raw) == str(caller_id):
        return caller_id, None

    has_org_perm = has_permission(f"{d.perm_prefix}.add.org")
    has_transorg_perm = has_permission(f"{d.perm_prefix}.add.all")
    if not has_org_perm and not has_transorg_perm:
        raise PermissionDenied()
    try:
        target_id = int(target_raw)
    except (TypeError, ValueError):
        return None, (jsonify({"success": False, "error": "Invalid userId"}), 400)

    if not has_transorg_perm:
        from . import engine_nexora_db

        nx_conn = engine_nexora_db.raw_connection()
        nx_cur = nx_conn.cursor()
        nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [target_id])
        row = nx_cur.fetchone()
        nx_cur.close()
        nx_conn.close()
        if not row or row[0] != session.get("organizationcode"):
            return None, (
                jsonify({"success": False, "error": "Target user not in your organization"}),
                403,
            )
    return target_id, None


# --------------------------------------------------------------------------- #
# View factories
# --------------------------------------------------------------------------- #


def _make_monthreport(d):
    spec = d.monthreport

    @require_permission(f"{d.perm_prefix}.view")
    def monthreport():
        conn = None
        try:
            from . import engine_generali_db

            if "username" not in session:
                return redirect(url_for("login"))

            ctx = _month_window()

            where_clauses = [f"{spec.date_column} >= ?", f"{spec.date_column} <= ?"]
            params: list = [str(ctx["first_day"]), str(ctx["last_day"])]
            if (
                spec.self_restrict
                and not has_permission(f"{d.perm_prefix}.edit.org")
                and not has_permission(f"{d.perm_prefix}.edit.all")
            ):
                where_clauses.append(f"{d.user_column} = ?")
                params.append(session.get("userid"))
            where_sql = "WHERE " + " AND ".join(where_clauses)

            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()
            if spec.group_column:
                cursor.execute(
                    f"""
            SELECT {spec.group_column},
                   {spec.measures}
            FROM {d.table}
            {where_sql}
            GROUP BY {spec.group_column}
            ORDER BY {spec.group_column}
        """,
                    params,
                )
                rows_raw = cursor.fetchall()
                cursor.close()
                rows = [spec.row_builder(r) for r in rows_raw]
                summary = spec.summary(rows)
            else:
                cursor.execute(
                    f"""
            SELECT {spec.measures}
            FROM {d.table}
            {where_sql}
        """,
                    params,
                )
                row = cursor.fetchone()
                cursor.close()
                rows = []
                summary = spec.summary(row)

            return render_template(
                "generali_monthreport.html",
                logged_in_user=session.get("username"),
                page_visibility=page_visibility(),
                section=spec.section,
                section_title=spec.section_title,
                back_url=url_for(spec.back_endpoint),
                year=ctx["year"],
                month=ctx["month"],
                month_label=ctx["month_label"],
                prev_year=ctx["prev_year"],
                prev_month=ctx["prev_month"],
                next_year=ctx["next_year"],
                next_month=ctx["next_month"],
                is_current_month=ctx["is_current_month"],
                summary=summary,
                rows=rows,
            )
        except Exception as e:
            current_app.logger.error(f"Error loading {d.monthreport_label} Month Report: {e}")
            return render_template("handlers/500.html"), 500
        finally:
            if conn:
                conn.close()

    return monthreport


def _make_org_users(d):
    @require_any_permission(f"{d.perm_prefix}.add.org", f"{d.perm_prefix}.add.all")
    def api_org_users():
        conn = None
        try:
            from . import engine_nexora_db

            transorg = has_permission(f"{d.perm_prefix}.add.all")
            org_code = session.get("organizationcode")
            if not transorg and not org_code:
                return jsonify({"success": False, "error": "No organization on session"}), 400

            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            if transorg:
                cursor.execute("SELECT userid, fullname FROM Users ORDER BY fullname")
            else:
                cursor.execute(
                    "SELECT userid, fullname FROM Users WHERE organizationcode = ? ORDER BY fullname",
                    [org_code],
                )
            users = [{"userId": row[0], "fullname": row[1]} for row in cursor.fetchall()]
            cursor.close()
            return jsonify({"success": True, "users": users})
        except Exception as e:
            current_app.logger.error(f"{d.label} OrgUsers Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_org_users


def _make_organizations(d):
    @require_permission(f"{d.perm_prefix}.view")
    def api_organizations():
        conn = None
        try:
            from . import engine_generali_db

            restrict_to_self = (
                d.organizations_restrict
                and not has_permission(f"{d.perm_prefix}.edit.org")
                and not has_permission(f"{d.perm_prefix}.edit.all")
            )
            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()
            if restrict_to_self:
                cursor.execute(
                    f"SELECT DISTINCT {d.user_column} FROM {d.table} "
                    f"WHERE {d.user_column} IS NOT NULL AND {d.user_column} = ?",
                    [session.get("userid")],
                )
            else:
                cursor.execute(
                    f"SELECT DISTINCT {d.user_column} FROM {d.table} "
                    f"WHERE {d.user_column} IS NOT NULL"
                )
            user_ids = [r[0] for r in cursor.fetchall()]
            cursor.close()
            return jsonify({"success": True, "organizations": _generali_orgs_for_userids(user_ids)})
        except Exception as e:
            current_app.logger.error(f"{d.label} Organizations Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_organizations


def _make_filter_users(d):
    @require_permission(f"{d.perm_prefix}.view")
    def api_filter_users():
        try:
            from . import engine_generali_db, engine_nexora_db

            transorg = has_permission(f"{d.perm_prefix}.edit.all")
            org_edit = has_permission(f"{d.perm_prefix}.edit.org")
            if not transorg and not org_edit:
                return jsonify({"success": True, "users": []})
            gen_conn = engine_generali_db.raw_connection()
            gen_cur = gen_conn.cursor()
            gen_cur.execute(
                f"SELECT DISTINCT {d.user_column} FROM {d.table} "
                f"WHERE {d.user_column} IS NOT NULL"
            )
            user_ids = [r[0] for r in gen_cur.fetchall()]
            gen_cur.close()
            gen_conn.close()
            if not user_ids:
                return jsonify({"success": True, "users": []})
            placeholders = ",".join(["?"] * len(user_ids))
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            if transorg:
                cursor.execute(
                    f"SELECT userid, fullname FROM Users WHERE userid IN ({placeholders}) ORDER BY fullname",
                    user_ids,
                )
            else:
                cursor.execute(
                    f"SELECT userid, fullname FROM Users WHERE userid IN ({placeholders}) AND organizationcode = ? ORDER BY fullname",
                    [*user_ids, session.get("organizationcode")],
                )
            users = [{"userId": row[0], "fullname": row[1]} for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return jsonify({"success": True, "users": users})
        except Exception as e:
            current_app.logger.error(f"{d.filter_users_label} FilterUsers Error: {e}")
            return _fail()

    return api_filter_users


def _list_where(d, spec):
    """(clauses, params) from the descriptor's ordered filter list + scope."""
    where_clauses = []
    params = []
    org_code = request.args.get("organizationcode", "").strip()
    for f in spec.filters:
        if f is SCOPE:
            scope_clauses, scope_params = _generali_scope_where(
                d.perm_prefix, d.user_column, org_code
            )
            where_clauses.extend(scope_clauses)
            params.extend(scope_params)
            continue
        if f.op == "eq_or_null":
            value = request.args.get(f.param, None)
            if value is None:
                continue
            if value == "":
                where_clauses.append(f"{f.column} IS NULL")
            else:
                where_clauses.append(f"{f.column} = ?")
                params.append(value)
            continue
        if f.op == "bool":
            value = request.args.get(f.param, "").strip().lower()
            if value in ("true", "false"):
                where_clauses.append(f"{f.column} = ?")
                params.append(1 if value == "true" else 0)
            continue
        value = request.args.get(f.param, "").strip()
        if not value:
            continue
        if f.op == "eq_in_set" and value not in f.allowed:
            continue
        op = {"gte": ">=", "lte": "<="}.get(f.op, "=")
        where_clauses.append(f"{f.column} {op} ?")
        params.append(value)
    return where_clauses, params


def _make_list(d):
    spec = d.list_spec

    @require_permission(f"{d.perm_prefix}.view")
    def api_list():
        conn = None
        try:
            from . import engine_generali_db

            page = max(1, int(request.args.get("page", 1)))
            per_page = 20
            offset = (page - 1) * per_page

            where_clauses, params = _list_where(d, spec)
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()

            agg_cols = "COUNT(*)"
            if spec.aggregate:
                agg_cols += f", {spec.aggregate[0]}"
            cursor.execute(f"SELECT {agg_cols} FROM {d.table} {where_sql}", params)
            agg = cursor.fetchone()
            assert agg is not None  # aggregate SELECT always returns exactly one row
            total_records = agg[0] or 0
            total_pages = max(1, -(-total_records // per_page))

            requested_all = request.args.get("all", "").lower() == "true"
            # Cap ?all=true at the export ceiling instead of returning every
            # matching row: non-breaking when total_records <= the cap (same
            # SQL as before), only the pathological case gets bounded.
            truncated = requested_all and total_records > ALL_EXPORT_CAP
            if truncated:
                pagination_sql = "OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
                sql_params = [*params, ALL_EXPORT_CAP]
            elif requested_all:
                pagination_sql = ""
                sql_params = params
            else:
                pagination_sql = "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
                sql_params = [*params, offset, per_page]
            cursor.execute(
                f"""
            SELECT {spec.select}
            FROM {d.table}
            {where_sql}
            ORDER BY {spec.order_by}
            {pagination_sql}
        """,
                sql_params,
            )

            rows = cursor.fetchall()
            cursor.close()

            user_ids = list({r[spec.user_index] for r in rows if r[spec.user_index] is not None})
            user_map = _lookup_users(user_ids, d.user_lookup_label)

            records = [spec.record(r, user_map.get(r[spec.user_index], {})) for r in rows]

            payload = {"success": True, "records": records}
            if truncated:
                payload["truncated"] = True
                payload["capped_at"] = ALL_EXPORT_CAP
            if spec.aggregate:
                payload[spec.aggregate[1]] = spec.aggregate[2](agg[1])
            payload["pagination"] = {
                "page": page,
                "per_page": per_page,
                "total_records": total_records,
                "total_pages": total_pages,
            }
            return jsonify(payload)
        except Exception as e:
            current_app.logger.error(f"{d.label} List Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_list


def _make_add(d):
    write = d.write

    @require_permission(f"{d.perm_prefix}.add")
    def api_add():
        conn = None
        try:
            from . import engine_generali_db

            body = request.get_json(force=True)
            for_date = body.get(write.date_json, "").strip()

            user_id, err = _resolve_target_user(d, body)
            if err:
                return err

            deadline_err = _check_add_deadline(for_date, f"{d.perm_prefix}.add.pastdeadline")
            if deadline_err:
                return jsonify({"success": False, "error": deadline_err}), 403

            values, err = _parse_write_body(d, body)
            if err:
                return err

            columns = []
            placeholders = []
            params = []
            for col in write.insert_order:
                columns.append(col)
                if col == "RecordDateTime":
                    placeholders.append("GETDATE()")
                    continue
                placeholders.append("?")
                params.append(user_id if col == d.user_column else values[col])

            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"""
            INSERT INTO {d.table}
                ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
        """,
                params,
            )
            conn.commit()
            cursor.close()

            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"{d.label} Add Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_add


def _make_edit(d):
    write = d.write

    @require_any_permission(f"{d.perm_prefix}.edit.org", f"{d.perm_prefix}.edit.all")
    def api_edit(record_id):
        conn = None
        try:
            from . import engine_generali_db

            body = request.get_json(force=True)
            values, err = _parse_write_body(d, body)
            if err:
                return err

            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()
            if not has_permission(f"{d.perm_prefix}.edit.all"):
                _check_generali_record_org(cursor, d.table, d.user_column, record_id)
            assignments = ", ".join(f"{col} = ?" for col in write.update_order)
            cursor.execute(
                f"""
            UPDATE {d.table}
            SET {assignments}
            WHERE ID = ?
        """,
                [*(values[col] for col in write.update_order), record_id],
            )
            conn.commit()
            cursor.close()

            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"{d.label} Edit Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_edit


def _make_delete(d):
    @require_any_permission(f"{d.perm_prefix}.delete.org", f"{d.perm_prefix}.delete.all")
    def api_delete(record_id):
        conn = None
        try:
            from . import engine_generali_db

            conn = engine_generali_db.raw_connection()
            cursor = conn.cursor()
            if not has_permission(f"{d.perm_prefix}.delete.all"):
                _check_generali_record_org(cursor, d.table, d.user_column, record_id)
            cursor.execute(f"DELETE FROM {d.table} WHERE ID = ?", [record_id])
            conn.commit()
            cursor.close()

            return jsonify({"success": True})
        except Exception as e:
            current_app.logger.error(f"{d.label} Delete Error: {e}")
            return _fail()
        finally:
            if conn:
                conn.close()

    return api_delete


def _build_views(d):
    views = {}
    if d.monthreport:
        views["monthreport"] = _make_monthreport(d)
    if d.has_org_users:
        views["org_users"] = _make_org_users(d)
    if d.organizations:
        views["organizations"] = _make_organizations(d)
    if d.filter_users:
        views["filter_users"] = _make_filter_users(d)
    if d.list_spec:
        views["list"] = _make_list(d)
    if d.write:
        views["add"] = _make_add(d)
        views["edit"] = _make_edit(d)
    if d.has_delete:
        views["delete"] = _make_delete(d)
    return views


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #

_ROUTES = [
    # key, url suffix, endpoint suffix, methods
    ("org_users", "/orgUsers", "org_users", ["GET"]),
    ("organizations", "/organizations", "organizations", ["GET"]),
    ("filter_users", "/filterUsers", "filter_users", ["GET"]),
    ("list", "", "list", ["GET"]),
    ("add", "", "add", ["POST"]),
    ("edit", "/<int:record_id>", "edit", ["PUT"]),
    ("delete", "/<int:record_id>", "delete", ["DELETE"]),
]


def register_crud(app, d):
    """Register every generated view of ``d`` under its historical URL+endpoint."""
    views = d.views
    if "monthreport" in views:
        app.add_url_rule(
            d.monthreport_url,
            endpoint=d.monthreport_endpoint,
            view_func=views["monthreport"],
        )
    for key, url_suffix, endpoint_suffix, methods in _ROUTES:
        if key not in views:
            continue
        app.add_url_rule(
            f"{d.api_base}{url_suffix}",
            endpoint=f"api_generali_{d.slug}_{endpoint_suffix}",
            view_func=views[key],
            methods=methods,
        )
