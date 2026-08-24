"""User-related helpers used across blueprints (avatar URL resolution, etc.)."""

import os

from flask import url_for

from .config import PATHS

# Uploaded avatars live under var/uploads/ (gitignored, excluded from the
# deploy mirror), not static/ -- static/ is `robocopy /MIR`'d from git on
# every deploy, which would silently delete every user's uploaded avatar on
# the next release (see nx_lib/views/profile.py's upload handler).
_AVATARS_DIR = PATHS.uploads / "avatars"


def resolve_user_icon_url(user_id):
    if not user_id:
        return url_for("static", filename="images/default-icon.png")

    filename_lower = f"{user_id}-icon.png"
    path_lower = os.path.join(_AVATARS_DIR, filename_lower)
    if os.path.exists(path_lower):
        timestamp = int(os.path.getmtime(path_lower))
        return url_for("user_avatar", user_id=user_id, v=timestamp)

    filename_upper = f"{user_id}-Icon.png"
    path_upper = os.path.join(_AVATARS_DIR, filename_upper)
    if os.path.exists(path_upper):
        timestamp = int(os.path.getmtime(path_upper))
        return url_for("user_avatar", user_id=user_id, v=timestamp)

    return url_for("static", filename="images/default-icon.png")
