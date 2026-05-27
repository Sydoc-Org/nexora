"""Notification endpoints: list unread and mark read."""

from flask import current_app, jsonify, request, session
from flask_babel import gettext as _

from ..db import engineNexoraDB


def get_notifications():
    if "userid" not in session:
        return jsonify({"error": _("Not authenticated")}), 401

    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT TOP 10 NotificationID, Message, Link, Icon, Timestamp
            FROM Notifications
            WHERE UserID = ? AND IsRead = 0
            ORDER BY Timestamp DESC
            """,
            (session["userid"],),
        )

        notifications = [
            dict(zip([column[0] for column in cursor.description], row))
            for row in cursor.fetchall()
        ]
        return jsonify(notifications)
    except Exception as e:
        current_app.logger.error(f"API Error fetching notifications: {e}")
        return jsonify({"error": _("Could not fetch notifications")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def mark_notifications_as_read():
    if "userid" not in session:
        return jsonify({"error": _("Not authenticated")}), 401

    data = request.get_json()
    notification_ids = data.get("ids")

    if not notification_ids or not isinstance(notification_ids, list):
        return jsonify({"error": _("Invalid payload")}), 400

    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        placeholders = ",".join(["?" for _id in notification_ids])

        query = f"""
            UPDATE Notifications
            SET IsRead = 1
            WHERE UserID = ? AND NotificationID IN ({placeholders})
        """

        params = [session["userid"]] + notification_ids
        cursor.execute(query, params)
        conn.commit()

        return jsonify({"success": True, "message": _("Notifications marked as read.")})
    except Exception as e:
        current_app.logger.error(f"API Error marking notifications as read: {e}")
        return jsonify({"error": _("Could not update notifications")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule(
        "/api/notifications", endpoint="get_notifications", view_func=get_notifications
    )
    app.add_url_rule(
        "/api/notifications/mark_as_read",
        endpoint="mark_notifications_as_read",
        view_func=mark_notifications_as_read,
        methods=["POST"],
    )
