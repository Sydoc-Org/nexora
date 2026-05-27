"""User-related helpers used across blueprints (avatar URL resolution, portal user lookup, etc.)."""

import os

from flask import current_app, session, url_for

from .db import engine_nexora_db
from .security import has_permission


def get_all_portal_users(from_request, action):
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        if has_permission(f"{from_request}.{action}"):
            if has_permission("admin.interact.users.all"):
                cursor.execute("SELECT userID, fullname FROM Users")
            else:
                cursor.execute(
                    "SELECT userID, fullname FROM Users WHERE organizationCode in (?, 'SYDC') AND accessid not in (1,2) ORDER BY fullname",
                    session.get("organizationcode"),
                )

        users = [
            dict(zip([column[0] for column in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]
        return users
    except Exception as e:
        current_app.logger.error(f"Failed to fetch all portal users: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def resolve_user_icon_url(user_id):
    if not user_id:
        return url_for("static", filename="images/default-icon.png")

    filename_lower = f"{user_id}-icon.png"
    path_lower = os.path.join(current_app.root_path, "static", "images", filename_lower)
    if os.path.exists(path_lower):
        timestamp = int(os.path.getmtime(path_lower))
        return url_for("static", filename=f"images/{filename_lower}", v=timestamp)

    filename_upper = f"{user_id}-Icon.png"
    path_upper = os.path.join(current_app.root_path, "static", "images", filename_upper)
    if os.path.exists(path_upper):
        timestamp = int(os.path.getmtime(path_upper))
        return url_for("static", filename=f"images/{filename_upper}", v=timestamp)

    return url_for("static", filename="images/default-icon.png")
