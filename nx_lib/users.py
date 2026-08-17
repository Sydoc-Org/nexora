"""User-related helpers used across blueprints (avatar URL resolution, etc.)."""

import os

from flask import current_app, url_for


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
