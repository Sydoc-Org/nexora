"""Reporting: saved-report CRUD, sharing, and the share-target typeahead
(beautify-phase-2a, Task 3).

``/api/reporting/reports[/<id>]``, its ``/shares[/<uid>]`` sub-resource, and
``/api/reporting/share_targets``. Split out of
``nx_lib/views/reporting/__init__.py`` — see that module's docstring for the
package's overall shape.
"""

import json
import re

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...security import require_permission


def _preview_summary(defn):
    """Shape facts a library card can show next to its thumbnail.

    Ids and counts only -- the labels are resolved client-side against the
    source catalog so they stay translated. Type-guarded for the same reason
    _preview_kind is: a malformed saved definition must not take the listing
    down. The raw definition still never leaves this endpoint.
    """
    if not isinstance(defn, dict):
        return {}
    if defn.get("kind") == "dashboard":
        # Dashboard library card: a compact layout sketch ({t: card type,
        # s: 12-col span} per card) so the client can draw a true miniature of
        # the dashboard instead of a generic placeholder. Type-guarded like
        # everything else here — a malformed card is skipped, not fatal.
        cards_raw = defn.get("cards")
        cards = cards_raw if isinstance(cards_raw, list) else []
        mini = []
        for c in cards[:12]:
            if not isinstance(c, dict):
                continue
            t = c.get("type") if isinstance(c.get("type"), str) else "bar"
            try:
                s = int(c.get("span") or 6)
            except (TypeError, ValueError):
                s = 6
            mini.append({"t": t, "s": max(1, min(12, s))})
        return {"cards": mini, "cardCount": len(cards)}
    cols_raw = defn.get("columns")
    cols = cols_raw if isinstance(cols_raw, list) else []
    grain = ""
    for c in cols:
        if isinstance(c, dict) and isinstance(c.get("grain"), str):
            grain = c["grain"]
            break
    return {
        "source": defn.get("source") if isinstance(defn.get("source"), str) else "",
        "grain": grain,
        "dimensions": len(cols),
        "metrics": len(defn["metrics"]) if isinstance(defn.get("metrics"), list) else 0,
        "filters": len(defn["filters"]) if isinstance(defn.get("filters"), list) else 0,
    }


def _preview_kind(defn):
    """Derive the library card badge/preview kind from a report definition.

    Mirrors the frontend's previewKindOf (templates/js/_reporting_simple_js.html)
    exactly: no breakdown columns -> 'total'; a grain or a date-ish field name
    on the first column -> 'line'; a pie/donut visualization -> 'donut';
    otherwise -> 'bar'.

    Saved definitions come from a JSON blob a caller wrote through the report
    editor API, which only checks the top level is a dict (see
    api_reports_create). Anything under 'columns' can be malformed (a corrupt
    row, a hand-edited DB value, a future schema change) so every access below
    is type-guarded — malformed shape falls back to a sensible default kind
    instead of raising and taking the whole library listing down with it.
    """
    if not isinstance(defn, dict):
        return "bar"
    cols = defn.get("columns") or []
    if not isinstance(cols, list) or not cols:
        return "total"
    first = cols[0]
    if not isinstance(first, dict):
        return "bar"
    field = first.get("field") or ""
    if not isinstance(field, str):
        field = ""
    if first.get("grain") or re.search(r"date", field, re.I):
        return "line"
    if defn.get("visualization") in ("pie", "donut"):
        return "donut"
    return "bar"


@require_permission("reporting.view")
def api_reports_list():
    """List reports the caller owns, plus any shared with them.

    A report is visible when the caller owns it, its Visibility is 'shared'
    (everyone with reporting.view), or it is explicitly shared with the caller.
    Each row is tagged owned / canEdit and carries the owner's name, the
    owner-only sharedCount (explicit per-user grants), plus a
    server-computed previewKind for the library card badge/thumbnail (derived
    from DefinitionJSON — the raw definition itself is never sent here).
    """
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.ReportID, r.Name, r.UpdatedAt, r.Visibility, r.OwnerUserID, "
            "       u.username AS OwnerName, "
            "       JSON_VALUE(r.DefinitionJSON, '$.kind') AS Kind, "
            "       r.DefinitionJSON, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 ELSE 0 END AS Owned, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 "
            "            WHEN s.CanEdit = 1 THEN 1 ELSE 0 END AS CanEdit, "
            "       (SELECT COUNT(*) FROM dbo.ReportShares sc "
            "         WHERE sc.ReportID = r.ReportID) AS ShareCount "
            "FROM dbo.Reports r "
            "JOIN dbo.Users u ON u.userID = r.OwnerUserID "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ? "
            "ORDER BY Owned DESC, r.UpdatedAt DESC",
            (userid, userid, userid, userid, userid),
        )
        rows = []
        for r in cur.fetchall():
            try:
                defn = json.loads(r.DefinitionJSON or "{}")
            except (TypeError, ValueError):
                defn = {}
            # Defense-in-depth: _preview_kind type-guards known malformed
            # shapes internally, but one corrupt saved definition must never
            # be able to 500 the whole library for every user, so a row that
            # still fails to serialize for any other reason is skipped and
            # logged rather than propagating up to the route-level except.
            try:
                rows.append(
                    {
                        "id": r.ReportID,
                        "name": r.Name,
                        "updatedAt": str(r.UpdatedAt),
                        "kind": r.Kind or "table",
                        "visibility": r.Visibility,
                        "owned": bool(r.Owned),
                        "canEdit": bool(r.CanEdit),
                        "ownerName": r.OwnerName,
                        # Owner-only: how many colleagues it is shared with,
                        # so the library can tag a report that is shared by
                        # explicit grant while Visibility is still private.
                        "sharedCount": int(r.ShareCount) if r.Owned else 0,
                        "previewKind": _preview_kind(defn),
                        "summary": _preview_summary(defn),
                    }
                )
            except Exception as row_err:
                current_app.logger.warning(
                    f"/api/reporting/reports list: skipping malformed report "
                    f"{r.ReportID}: {row_err}"
                )
        return jsonify(rows)
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports list error: {e}")
        return jsonify({"error": _("Could not list reports")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_get(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT r.Name, r.DefinitionJSON, r.Visibility, r.OwnerUserID, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 ELSE 0 END AS Owned, "
            "       CASE WHEN r.OwnerUserID = ? THEN 1 "
            "            WHEN s.CanEdit = 1 THEN 1 ELSE 0 END AS CanEdit "
            "FROM dbo.Reports r "
            "LEFT JOIN dbo.ReportShares s "
            "       ON s.ReportID = r.ReportID AND s.SharedWithUserID = ? "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR r.Visibility = 'shared' OR s.SharedWithUserID = ?)",
            (userid, userid, userid, report_id, userid, userid),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": _("Not found")}), 404
        return jsonify(
            {
                "id": report_id,
                "name": row.Name,
                "definition": json.loads(row.DefinitionJSON),
                "visibility": row.Visibility,
                "owned": bool(row.Owned),
                "canEdit": bool(row.CanEdit),
            }
        )
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports get error: {e}")
        return jsonify({"error": _("Could not load report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_create():
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    definition_json = json.dumps(rd, ensure_ascii=False)
    if len(definition_json) > 64_000:
        return jsonify({"error": _("Report definition too large")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Reports (OwnerUserID, Name, DefinitionJSON) OUTPUT INSERTED.ReportID VALUES (?, ?, ?)",
            (userid, name, definition_json),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        new_id = inserted[0]
        conn.commit()
        return jsonify({"id": new_id, "ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports create error: {e}")
        return jsonify({"error": _("Could not save report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_update(report_id):
    userid = session.get("userid")
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    rd = payload.get("definition")
    if not name or not isinstance(rd, dict):
        return jsonify({"error": _("name and definition are required")}), 400
    definition_json = json.dumps(rd, ensure_ascii=False)
    if len(definition_json) > 64_000:
        return jsonify({"error": _("Report definition too large")}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        # Owner, or a colleague the owner shared it with for editing.
        cur.execute(
            "UPDATE r SET Name = ?, DefinitionJSON = ?, UpdatedAt = SYSUTCDATETIME() "
            "FROM dbo.Reports r "
            "WHERE r.ReportID = ? "
            "  AND (r.OwnerUserID = ? OR EXISTS ("
            "        SELECT 1 FROM dbo.ReportShares s "
            "        WHERE s.ReportID = r.ReportID AND s.SharedWithUserID = ? AND s.CanEdit = 1))",
            (name, definition_json, report_id, userid, userid),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports update error: {e}")
        return jsonify({"error": _("Could not update report")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
def api_reports_delete(report_id):
    userid = session.get("userid")
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM Reports WHERE ReportID = ? AND OwnerUserID = ?",
            (report_id, userid),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports delete error: {e}")
        return jsonify({"error": _("Could not delete report")}), 500
    finally:
        conn.close()


def _is_report_owner(report_id, userid):
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM dbo.Reports WHERE ReportID = ? AND OwnerUserID = ?",
            (report_id, userid),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def _resolve_user(identifier):
    """Resolve a username or email to {userId, name}, or None if unknown."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 userID, username, Fullname FROM dbo.Users "
            "WHERE username = ? OR Email = ?",
            (ident, ident),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"userId": row.userID, "name": row.Fullname or row.username}
    finally:
        conn.close()


def _shares_payload(report_id):
    """Current sharing state for a report: {visibility, shares:[...]}."""
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT Visibility FROM dbo.Reports WHERE ReportID = ?", (report_id,))
        row = cur.fetchone()
        visibility = row.Visibility if row else "private"
        cur.execute(
            "SELECT s.SharedWithUserID, s.CanEdit, u.username, u.Fullname "
            "FROM dbo.ReportShares s JOIN dbo.Users u ON u.userID = s.SharedWithUserID "
            "WHERE s.ReportID = ? ORDER BY u.username",
            (report_id,),
        )
        shares = [
            {
                "userId": r.SharedWithUserID,
                "name": r.Fullname or r.username,
                "username": r.username,
                "canEdit": bool(r.CanEdit),
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    return {"visibility": visibility, "shares": shares}


@require_permission("reporting.view")
def api_reports_shares_get(report_id):
    userid = session.get("userid")
    # 404 (not 403) for non-owners so a report's existence isn't leaked.
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    return jsonify(_shares_payload(report_id))


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_shares_set(report_id):
    """Owner sets a report's visibility and/or adds/updates one user share."""
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    payload = request.get_json(silent=True) or {}
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        visibility = payload.get("visibility")
        if visibility is not None:
            if visibility not in ("private", "shared"):
                return jsonify({"error": _("Invalid visibility")}), 400
            cur.execute(
                "UPDATE dbo.Reports SET Visibility = ? WHERE ReportID = ?",
                (visibility, report_id),
            )
        user_ident = payload.get("user")
        if user_ident:
            target = _resolve_user(user_ident)
            if not target:
                return jsonify({"error": _("User not found")}), 404
            if str(target["userId"]) == str(userid):
                return jsonify({"error": _("Cannot share a report with yourself")}), 400
            can_edit = 1 if payload.get("canEdit") else 0
            cur.execute(
                "SELECT 1 FROM dbo.ReportShares WHERE ReportID = ? AND SharedWithUserID = ?",
                (report_id, target["userId"]),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE dbo.ReportShares SET CanEdit = ? "
                    "WHERE ReportID = ? AND SharedWithUserID = ?",
                    (can_edit, report_id, target["userId"]),
                )
            else:
                cur.execute(
                    "INSERT INTO dbo.ReportShares (ReportID, SharedWithUserID, CanEdit) "
                    "VALUES (?, ?, ?)",
                    (report_id, target["userId"], can_edit),
                )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports shares set error: {e}")
        return jsonify({"error": _("Could not update sharing")}), 500
    finally:
        conn.close()
    return jsonify(_shares_payload(report_id))


@require_permission("reporting.view")
def api_reports_shares_delete(report_id, share_user_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportShares WHERE ReportID = ? AND SharedWithUserID = ?",
            (report_id, share_user_id),
        )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"/api/reporting/reports shares delete error: {e}")
        return jsonify({"error": _("Could not update sharing")}), 500
    finally:
        conn.close()
    return jsonify(_shares_payload(report_id))


@require_permission("reporting.view")
@limiter.limit("30 per minute")
def api_share_targets():
    """Typeahead for the share modal: up to 8 users matching by username,
    full name or email. Returns only username + display name — the share
    POST already accepts the username."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 8 username, Fullname FROM dbo.Users "
            "WHERE username LIKE ? OR Fullname LIKE ? OR Email LIKE ? "
            "ORDER BY username",
            (like, like, like),
        )
        return jsonify(
            [{"username": r.username, "name": r.Fullname or r.username} for r in cur.fetchall()]
        )
    except Exception as e:
        current_app.logger.error(f"reporting share targets error: {e}")
        return jsonify([])
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/reports",
        endpoint="reporting_reports_list",
        view_func=api_reports_list,
    )
    app.add_url_rule(
        "/api/reporting/reports",
        endpoint="reporting_reports_create",
        view_func=api_reports_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_get",
        view_func=api_reports_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_update",
        view_func=api_reports_update,
        methods=["PUT"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>",
        endpoint="reporting_reports_delete",
        view_func=api_reports_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares",
        endpoint="reporting_reports_shares_get",
        view_func=api_reports_shares_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares",
        endpoint="reporting_reports_shares_set",
        view_func=api_reports_shares_set,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/shares/<int:share_user_id>",
        endpoint="reporting_reports_shares_delete",
        view_func=api_reports_shares_delete,
        methods=["DELETE"],
    )
    app.add_url_rule(
        "/api/reporting/share_targets",
        endpoint="reporting_share_targets",
        view_func=api_share_targets,
    )
