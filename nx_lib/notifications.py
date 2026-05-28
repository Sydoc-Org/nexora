"""Notification creation helper. Used by chat/workitem routes to push
notifications into the Notifications table without circular imports between
view modules."""

from flask import current_app

from .db import engine_nexora_db


def create_notification(user_id, message, link=None, icon="fa-info-circle"):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Notifications (UserID, Message, Link, Icon)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, message, link, icon),
        )
        conn.commit()
    except Exception as e:
        current_app.logger.error(f"Failed to create notification for UserID {user_id}: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
