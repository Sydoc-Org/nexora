"""Core routes that don't fit a larger domain: landing page, jdvance,
public maintenance view, session liveness probe, API documentation page,
org-branding logo serve, terms of service and privacy policy."""

import os

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    send_from_directory,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..branding import brand_for_org
from ..config import PATHS
from ..db import engine_nexora_db
from ..maintenance import _get_blocking_maintenance, _maintenance_iso
from ..security import page_visibility, require_permission, startpage_redirect_to


def index():
    if "username" in session:
        return redirect(url_for(startpage_redirect_to(page_visibility())))
    return render_template("hero.html")


def legal_terms():
    """Terms of service. Deliberately NOT permission-gated and reachable

    signed out: it is linked from the footer of the login and 2FA screens,
    where there is no session yet. The page renders no user data.
    """
    return render_template("legal.html", doc="terms", page_title=_("Terms of Service"))


def legal_privacy():
    """Privacy policy. Public for the same reason as legal_terms(), and

    additionally because a privacy notice that can only be read after signing
    in cannot inform the decision to sign in.
    """
    return render_template("legal.html", doc="privacy", page_title=_("Privacy Policy"))


@require_permission("jd.view")
def jdvance():
    return render_template("jd/jdvance.html")


@require_permission("api.docs.view")
def api_docs():
    return render_template(
        "api_docs.html",
        page_visibility=page_visibility(),
        logged_in_user=session.get("username", "Unknown"),
        userid=session.get("userid", "Unknown"),
    )


def maintenance_page():
    blocking = _get_blocking_maintenance()
    return render_template("maintenance.html", maintenance=blocking), (503 if blocking else 200)


def api_maintenance_active():
    conn = None
    cursor = None
    try:
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        # Priority 1: currently active banner (window has started)
        cursor.execute(
            """
            SELECT TOP 1 ID, Title, Message, StartAt, EndAt, Severity
            FROM MaintenanceBanner
            WHERE Active = 1
              AND StartAt <= GETDATE()
              AND EndAt   >= GETDATE()
            ORDER BY StartAt DESC, ID DESC
            """
        )
        row = cursor.fetchone()
        if row:
            rec_id, title, message, start_at, end_at, severity = row
            return jsonify(
                {
                    "success": True,
                    "banner": {
                        "id": int(rec_id),
                        "title": title,
                        "message": message,
                        "startAt": _maintenance_iso(start_at),
                        "endAt": _maintenance_iso(end_at),
                        "severity": severity,
                        "upcoming": False,
                    },
                }
            )
        # Priority 2: upcoming banner within its announcement window
        cursor.execute(
            """
            SELECT TOP 1 ID, Title, Message, StartAt, EndAt, Severity
            FROM MaintenanceBanner
            WHERE Active = 1
              AND StartAt > GETDATE()
              AND AnnounceMinutesBefore > 0
              AND DATEADD(minute, -AnnounceMinutesBefore, StartAt) <= GETDATE()
            ORDER BY StartAt ASC, ID ASC
            """
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": True, "banner": None})
        rec_id, title, message, start_at, end_at, severity = row
        return jsonify(
            {
                "success": True,
                "banner": {
                    "id": int(rec_id),
                    "title": title,
                    "message": message,
                    "startAt": _maintenance_iso(start_at),
                    "endAt": _maintenance_iso(end_at),
                    "severity": severity,
                    "upcoming": True,
                },
            }
        )
    except Exception as e:
        current_app.logger.error(f"Maintenance active error: {e}")
        return jsonify({"success": False, "error": "internal error"}), 500
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        if conn:
            conn.close()


def branding_logo(orgcode):
    """Serve an organization's uploaded logo from var/branding/ (#98 phase 4).

    Permission-free beyond requiring a logged-in session -- any logged-in
    user must be able to see their (or another visible org's) brand image,
    same idiom as /avatar/<user_id>. The upload side lands in Task 11; this
    is the minimal read side so Task 10's header <img src> has a live
    endpoint to point at.

    Path-traversal hardening: ``orgcode`` never touches the filesystem
    directly -- it is only ever used as a dict key into branding.brand_for_org,
    so a hostile value simply misses (404) instead of resolving a path. The
    stored BrandLogoFile name is defended too (os.path.basename), even though
    Task 11's upload path is expected to only ever write ``<orgcode>.<ext>``.

    Served with a sandboxed CSP + nosniff (spec D9): SVG is allowed and is
    script-capable, so the response must never be treated as same-origin
    executable content.

    The sandbox CSP is set twice on purpose, see BRANDING_LOGO_CSP below.
    """
    if "userid" not in session:
        abort(401)
    brand = brand_for_org(orgcode)
    if not brand or not brand.get("logo_file"):
        abort(404)
    filename = os.path.basename(brand["logo_file"])
    if not filename or not (PATHS.branding / filename).is_file():
        abort(404)
    # The header fetches this on every page load of a branded org, so it must
    # not cost a conditional round-trip per view. Flask's default max_age is
    # None (revalidate every time); one hour is short enough that replacing a
    # logo shows up the same working day and long enough to keep the header
    # image out of the request log entirely (nx_lib/hooks.py skips /branding
    # the same way it skips /avatar).
    resp = send_from_directory(PATHS.branding, filename, max_age=BRANDING_LOGO_MAX_AGE)
    resp.headers["Content-Security-Policy"] = BRANDING_LOGO_CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


# The one control that makes script-capable SVG safe to serve (spec D9), so it
# has to reach the client in BOTH environments -- and the two environments need
# two different mechanisms:
#
# * INT/dev/TEST have no CSP at all: the header the view sets above is the whole
#   story, and nothing overwrites it.
# * PROD installs Talisman (nx_lib/__init__.py), whose after_request assigns
#   Content-Security-Policy *unconditionally* -- no setdefault, no
#   already-present guard. It runs after the view, so the view's header would be
#   silently replaced by the global policy, whose script-src permits jsdelivr /
#   cdnjs / tailwindcss. An uploaded SVG navigated to directly could then pull
#   attacker-chosen remote code onto the app origin.
#
# talisman_view_options is Talisman's own per-view override hook (what its
# @talisman(...) decorator sets): _get_local_options() reads it off the resolved
# view function, so the sandbox policy wins over the global one for this
# endpoint only. content_security_policy_nonce_in is emptied so no script-src
# nonce is appended to a policy that has no script-src.
#
# Talisman renders a dict policy as "<section> <content>", i.e. "sandbox " with
# a trailing space; the view sets the bare token. Compare stripped.
BRANDING_LOGO_CSP = "sandbox"

# Cache-Control max-age for the served brand logo, in seconds (one hour).
BRANDING_LOGO_MAX_AGE = 3600
branding_logo.talisman_view_options = {  # type: ignore[attr-defined]
    "content_security_policy": {BRANDING_LOGO_CSP: ""},
    "content_security_policy_nonce_in": [],
}


def session_heartbeat():
    """Lightweight liveness probe. Authenticated pages poll this every few
    seconds; if the session was revoked, enforce_active_session has already
    returned 401, so the client redirects to /login."""
    if "userid" not in session:
        return jsonify({"ok": False, "reason": "unauthenticated"}), 401
    return jsonify({"ok": True})


def register_routes(app):
    app.add_url_rule("/", endpoint="index", view_func=index)
    app.add_url_rule("/jdvance", endpoint="jdvance", view_func=jdvance)
    app.add_url_rule("/api-docs", endpoint="api_docs", view_func=api_docs)
    app.add_url_rule("/terms", endpoint="legal_terms", view_func=legal_terms)
    app.add_url_rule("/privacy", endpoint="legal_privacy", view_func=legal_privacy)
    app.add_url_rule("/maintenance", endpoint="maintenance_page", view_func=maintenance_page)
    app.add_url_rule(
        "/api/maintenance/active",
        endpoint="api_maintenance_active",
        view_func=api_maintenance_active,
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/session/heartbeat", endpoint="session_heartbeat", view_func=session_heartbeat
    )
    app.add_url_rule("/branding/<orgcode>/logo", endpoint="branding_logo", view_func=branding_logo)
