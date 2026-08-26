"""Request lifecycle hooks, error handlers, and template context processors.

All these functions are registered against the Flask app inside ``init_app``.
"""

import csv
import time
from datetime import datetime

from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import user_cache
from .config import IS_PROD, PATHS
from .db import engine_nexora_db
from .i18n import get_locale
from .maintenance import (
    _MAINTENANCE_LOCKOUT_SKIP_PATHS,
    _get_blocking_maintenance,
    _user_has_maintenance_bypass,
)
from .security import (
    PermissionDenied,
    has_permission,
    load_permissions_for_user,
)
from .ui_prefs import load_ui_prefs
from .users import resolve_user_icon_url
from .version import BUILD_STAMP, __version__
from .whats_new import has_unseen, load_seen_version

_SESSION_ENFORCE_SKIP_PATHS = (
    "/static",
    "/avatar",
    "/login",
    "/logout",
    "/forgot_password",
    "/set_new_password",
    "/init_reset",
    "/init_2FA",
    "/verify_2fa",
    "/reset_password",
    "/dev/login",
    "/dev/users",
)


def get_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(",")[0]
    return request.remote_addr or "Unknown"


def _start_timer():
    request.start_time = time.time()


def _enforce_active_session():
    """If a logged-in user's SID is no longer in ActiveSessions (e.g. an admin
    revoked it), clear the session and redirect/401. Backend-agnostic: this is
    what makes force-logout actually take effect on the next request.

    Also bumps LastSeenAt (at most once per cache TTL) so the admin "active
    sessions" view reflects recent activity rather than just login time (#109)."""
    if request.path.startswith(_SESSION_ENFORCE_SKIP_PATHS):
        return
    if "userid" not in session:
        return
    sid = getattr(session, "sid", None) or session.get("_dev_sid")
    if not sid:
        return

    def _check_and_bump():
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ActiveSessions SET LastSeenAt = GETDATE() WHERE SessionID = ?",
            (str(sid),),
        )
        updated = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return bool(updated)

    # Cached per SID (nx_lib/user_cache.py): this UPDATE+commit on every request
    # was the single hottest per-request cost (~70 of 75 ms in profile). An
    # admin revocation still lands within one request: revoke goes through an
    # /admin write, which clears the whole cache (_invalidate_user_cache);
    # otherwise a revoked SID is caught at worst one TTL (30 s) later.
    # LastSeenAt is now bumped at most once per TTL per session — the admin
    # "active sessions" view lags actual activity by up to that much.
    try:
        alive = user_cache.get_or_load("session_alive", sid, _check_and_bump)
    except Exception as e:
        current_app.logger.warning(f"enforce_active_session check failed: {e}")
        return  # Fail open — never lock users out due to a transient DB blip
    if alive:
        return
    session.clear()
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Session revoked", "reason": "revoked"}), 401
    return redirect(url_for("login"))


def _reload_user_permissions():
    """Refresh session['permissions'] on every non-static request, served from
    the per-process TTL cache (nx_lib/user_cache.py) so ~500 users no longer
    mean one spGetUserPermissions round-trip per click and per heartbeat.
    _invalidate_user_cache() drops entries the moment an admin writes."""
    if request.path.startswith(("/static", "/avatar")):
        return
    if "userid" in session:
        uid = str(session["userid"])
        try:
            session["permissions"] = user_cache.get_or_load(
                "permissions", uid, lambda: load_permissions_for_user(uid)
            )
        except Exception as e:
            current_app.logger.error(f"reload_user_permissions error: {e}")


def _load_user_locale():
    if "userid" in session and "locale" not in session:
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT locale FROM Users WHERE userid = ?", [session["userid"]])
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row[0] in ["de", "en", "fr", "it"]:
                session["locale"] = row[0]
        except Exception as e:
            current_app.logger.error(f"load_user_locale error: {e}")


def _load_user_ui_prefs():
    """Refresh UI prefs on every request (same idiom as permissions), through
    the per-process TTL cache. The cache must NOT live in the session: concurrent
    requests (e.g. the 5s heartbeat) race the session cookie and can resurrect
    old prefs, making saves look non-persistent (#155). A process-local dict has
    no such race, and POST /profile/ui_prefs drops the user's entry
    (_invalidate_user_cache) so a save shows on the very next request."""
    if request.path.startswith(("/static", "/avatar")):
        return
    if "userid" in session:
        uid = session["userid"]
        session["ui_prefs"] = user_cache.get_or_load("ui_prefs", uid, lambda: load_ui_prefs(uid))


def _invalidate_user_cache(resp):
    """Keep the process cache honest after writes: a user's own pref save drops
    their entries; ANY admin write drops everything, because access profiles and
    permission edits fan out to many users and it is not worth tracking which.
    Paths are unprefixed here (PrefixMiddleware already stripped /nexora)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return resp
    if request.path.startswith("/admin"):
        user_cache.clear()
    elif request.path == "/profile/ui_prefs" and "userid" in session:
        user_cache.forget(session["userid"])
    return resp


def _enforce_maintenance_lockout():
    """When a banner with BlockAccess=1 is in its window, kick non-bypass users
    out of every route except a tiny allowlist (login is handled inside login())."""
    if request.path.startswith(_MAINTENANCE_LOCKOUT_SKIP_PATHS):
        return
    blocking = _get_blocking_maintenance()
    if not blocking:
        return
    # Established session
    if has_permission("admin.maintenance.bypass"):
        return
    # Mid-login flow (after bcrypt success, before perms are loaded into session)
    pending_uid = session.get("pre_2fa_userid") or session.get("pre_auth_userid")
    if pending_uid and _user_has_maintenance_bypass(pending_uid):
        return
    # Drop their session so they can't keep working anywhere
    if "userid" in session:
        session.clear()
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Maintenance", "maintenance": blocking}), 503
    return render_template("maintenance.html", maintenance=blocking), 503


def _log_every_request(response):
    if request.path.startswith(("/static", "/avatar")):
        return response
    duration = time.time() - request.start_time if hasattr(request, "start_time") else 0

    try:
        logs_hour_folder = PATHS.logs / "user" / datetime.now().strftime("%Y%m%d%H")
        logs_hour_folder.mkdir(parents=True, exist_ok=True)

        with (logs_hour_folder / "nexora_logs.csv").open("a", newline="") as csvfile:
            fieldnames = [
                "SessionID",
                "RequestIpAddress",
                "UserID",
                "Username",
                "HttpRequestMethod",
                "Path",
                "HttpResponseCode",
                "Args",
                "durationSeconds",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if csvfile.tell() == 0:
                writer.writeheader()
            writer.writerow(
                {
                    "SessionID": session.get("uuid"),
                    "RequestIpAddress": get_ip(),
                    "UserID": session.get("userid"),
                    "Username": session.get("username"),
                    "HttpRequestMethod": request.method,
                    "Path": request.path,
                    "HttpResponseCode": response.status_code,
                    "Args": request.args.to_dict(),
                    "durationSeconds": round(duration, 4),
                }
            )
    except Exception as e:
        current_app.logger.error(f"Logging failed: {e}")
    return response


def _is_external_api_path(path):
    # The external machine-to-machine API (/api/v1 and its /api/test/v1
    # sandbox twin) gets JSON error bodies (same idiom as the session-
    # revoked/maintenance hooks above). NOT gated on /api/ broadly, so the
    # legacy internal /api/* surfaces keep their current HTML behavior.
    return path.startswith("/api/v1") or path.startswith("/api/test/v1")


def _page_not_found(e):
    if _is_external_api_path(request.path):
        return jsonify({"error": "Not found"}), 404
    return render_template("handlers/404.html"), 404


def _internal_error(e):
    if _is_external_api_path(request.path):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("handlers/500.html"), 500


def _forbidden_page(e):
    if _is_external_api_path(request.path):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("handlers/403.html"), 403


def _handle_permission_denied(e):
    if _is_external_api_path(request.path):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("handlers/403.html"), 403


def _inject_current_lang():
    return {"current_lang": str(get_locale())}


def _inject_ui_prefs():
    return {"ui_prefs": session.get("ui_prefs") or {}}


def _utility_processor():
    return dict(
        get_user_icon_url=resolve_user_icon_url, has_permission=has_permission, is_prod=IS_PROD
    )


def _inject_app_version():
    return {"nexora_version": __version__, "nexora_build": BUILD_STAMP}


def _inject_whats_new():
    """Header badge: unseen curated release notes. Read fresh from the DB per
    render (permissions/ui_prefs idiom — a session cache races the cookie and
    resurrects the dot after it was cleared)."""
    if "userid" not in session:
        return {"whats_new_unseen": False}
    seen = load_seen_version(session["userid"])
    return {"whats_new_unseen": has_unseen(seen, has_permission)}


def init_app(app):
    app.before_request(_start_timer)
    app.before_request(_enforce_active_session)
    app.before_request(_reload_user_permissions)
    app.before_request(_load_user_locale)
    app.before_request(_load_user_ui_prefs)
    app.before_request(_enforce_maintenance_lockout)
    app.after_request(_invalidate_user_cache)
    app.after_request(_log_every_request)

    app.register_error_handler(404, _page_not_found)
    app.register_error_handler(500, _internal_error)
    app.register_error_handler(403, _forbidden_page)
    app.register_error_handler(PermissionDenied, _handle_permission_denied)

    app.context_processor(_inject_current_lang)
    app.context_processor(_inject_ui_prefs)
    app.context_processor(_utility_processor)
    app.context_processor(_inject_app_version)
    app.context_processor(_inject_whats_new)
