"""Reporting: chart annotations (#284).

``/api/reporting/reports/<id>/annotations[/<aid>]`` -- a report owner pins a
short note on one chart bucket; anyone who can open the report reads them.
Writes are gated by ``reports._is_report_owner``, reads by
``reports._can_view_report``. No permission code of its own (spec D2).
"""

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ...db import engine_nexora_db
from ...extensions import limiter
from ...security import require_permission
from .reports import _can_view_report, _is_report_owner

TEXT_MAX = 500
BUCKET_MAX = 64


def _serialize(r):
    return {
        "id": r.AnnotationID,
        "bucket": r.BucketKey,
        "text": r.Text,
        "author": r.Author,
        "createdAt": str(r.CreatedAt) if r.CreatedAt else None,
    }


def _validate(p):
    """Return (bucket, text) or raise ValueError with a user-facing message.

    ponytail: format-only validation; the server does not re-run the report to
    check the bucket exists. Add that if orphan rows ever show up.
    """
    bucket = str(p.get("bucket") or "").strip()
    text = str(p.get("text") or "").strip()
    if not bucket:
        raise ValueError(_("Pick a bucket on the chart."))
    if len(bucket) > BUCKET_MAX:
        raise ValueError(_("This bucket label is too long to annotate."))
    if not text:
        raise ValueError(_("Annotation text is required."))
    if len(text) > TEXT_MAX:
        raise ValueError(_("Annotation text is limited to 500 characters."))
    return bucket, text


@require_permission("reporting.view")
def api_reports_annotations_get(report_id):
    userid = session.get("userid")
    if not _can_view_report(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT a.AnnotationID, a.BucketKey, a.Text, a.CreatedAt, "
            "       u.Fullname AS Author "
            "FROM dbo.ReportAnnotations a "
            "JOIN dbo.Users u ON u.userID = a.CreatedBy "
            "WHERE a.ReportID = ? "
            "ORDER BY a.BucketKey, a.AnnotationID",
            (report_id,),
        )
        return jsonify([_serialize(r) for r in cur.fetchall()])
    except Exception as e:
        current_app.logger.error(f"reporting annotations list error: {e}")
        return jsonify({"error": _("Could not list annotations")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_annotations_create(report_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    try:
        bucket, text = _validate(request.get_json(silent=True) or {})
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.ReportAnnotations (ReportID, BucketKey, Text, CreatedBy) "
            "OUTPUT INSERTED.AnnotationID VALUES (?, ?, ?, ?)",
            (report_id, bucket, text, userid),
        )
        inserted = cur.fetchone()
        assert inserted is not None  # INSERT ... OUTPUT always returns the new row
        conn.commit()
        return jsonify({"id": inserted[0], "ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting annotations create error: {e}")
        return jsonify({"error": _("Could not save annotation")}), 500
    finally:
        conn.close()


@require_permission("reporting.view")
@limiter.limit("60 per minute")
def api_reports_annotations_delete(report_id, annotation_id):
    userid = session.get("userid")
    if not _is_report_owner(report_id, userid):
        return jsonify({"error": _("Not found")}), 404
    conn = engine_nexora_db.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM dbo.ReportAnnotations WHERE AnnotationID = ? AND ReportID = ?",
            (annotation_id, report_id),
        )
        affected = cur.rowcount
        conn.commit()
        if not affected:
            return jsonify({"error": _("Not found")}), 404
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"reporting annotations delete error: {e}")
        return jsonify({"error": _("Could not delete annotation")}), 500
    finally:
        conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations",
        endpoint="reporting_reports_annotations_get",
        view_func=api_reports_annotations_get,
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations",
        endpoint="reporting_reports_annotations_create",
        view_func=api_reports_annotations_create,
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/reporting/reports/<int:report_id>/annotations/<int:annotation_id>",
        endpoint="reporting_reports_annotations_delete",
        view_func=api_reports_annotations_delete,
        methods=["DELETE"],
    )
