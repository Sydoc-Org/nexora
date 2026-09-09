"""Profile, password change, language switch, feedback."""

import io
import os
import re
from html import escape

import bcrypt
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_babel import gettext as _
from PIL import Image
from werkzeug.utils import secure_filename

from ..config import PATHS, SUPPORT_MAIL
from ..db import engine_nexora_db
from ..extensions import limiter
from ..files import is_file_allowed
from ..mail import MailError, send_mail
from ..security import has_permission, page_visibility
from ..ui_prefs import sanitize_ui_prefs, save_ui_prefs
from ..version import BUILD_STAMP, __version__
from ..whats_new import mark_seen, visible_releases


def profile():
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        logged_in_user = session.get("username", "Unknown")
        userid = session.get("userid", "Unknown")
        fullname = session.get("fullname", "Unknown")
        email = session.get("email", "Unknown")
        return render_template(
            "profile.html",
            userid=userid,
            logged_in_user=logged_in_user,
            fullname=fullname,
            email=email,
            page_visibility=page_visibility(),
        )
    except Exception:
        return render_template("500.html")


def update_profile():
    conn = None
    cursor = None
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        if request.method == "POST":
            userid = session["userid"]
            username = session["username"]
            # Defence-in-depth against a stored-XSS payload in the display name
            # (#193): the dashboard HTML-escapes it now, but also bound its
            # length here so an absurd value can't be stored. Silent cap (no new
            # user-facing string) -- names past 100 chars aren't realistic.
            fullname = request.form["fullName"].strip()[:100]
            email = request.form["email"]

            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()

            if (
                not re.search(r"^((?!\.)[\w\-_.]*[^.])(@\w+)(\.\w+(\.\w+)?[^.\W])$", email)
                or len(email) >= 50
            ):
                flash(_("Email Adress is not valid"), "failure_updateProfile")
                return redirect(url_for("profile"))

            cursor.execute("SELECT 0 FROM Users WHERE Email = ? and userid <> ?", (email, userid))
            row = cursor.fetchone()

            if row:
                flash(_("Email Adress is already in use"), "failure_updateProfile")
                return redirect(url_for("profile"))

            cursor.execute(
                """
                UPDATE Users
                SET fullname = ?, email = ?
                WHERE username = ?
                """,
                (fullname, email, username),
            )

            conn.commit()

            session["fullname"] = fullname
            session["email"] = email

            if "file" in request.files and request.files["file"].filename != "":
                f = request.files["file"]
                if not is_file_allowed(f.filename, f.stream):
                    flash(
                        _("Invalid file format. Please upload a valid image."),
                        "failure_updateProfile",
                    )
                    return redirect(url_for("profile"))
                try:
                    in_memory_file = io.BytesIO()
                    f.save(in_memory_file)
                    in_memory_file.seek(0)

                    img = Image.open(in_memory_file)
                    img.verify()

                    filename = f"{userid}-icon.png"
                    avatars_dir = PATHS.uploads / "avatars"
                    avatars_dir.mkdir(parents=True, exist_ok=True)
                    abs_path = os.path.join(avatars_dir, filename)
                    if os.path.exists(abs_path):
                        os.remove(abs_path)

                    in_memory_file.seek(0)
                    with open(abs_path, "wb") as disk_file:
                        disk_file.write(in_memory_file.read())
                except Exception as e:
                    current_app.logger.error(f"Invalid image upload attempt by user {userid}: {e}")
                    flash(
                        _("Invalid file format. Please upload a valid image."),
                        "failure_updateProfile",
                    )
                    return redirect(url_for("profile"))
            flash(_("Profile updated successfully!"), "success_updateProfile")
            return redirect(url_for("profile"))

        return redirect(url_for("profile"))
    except Exception:
        flash(_("Unexpected error"), "failure_updateProfile")
        return redirect(url_for("profile"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def user_avatar(user_id):
    """Serve an uploaded avatar from var/uploads/avatars/ (see resolve_user_icon_url).

    Not under static/ on purpose -- static/ is robocopy-mirrored from git on
    every deploy, which would delete every uploaded avatar on the next release.
    """
    if "userid" not in session:
        abort(401)
    avatars_dir = PATHS.uploads / "avatars"
    for filename in (f"{user_id}-icon.png", f"{user_id}-Icon.png"):
        if (avatars_dir / filename).exists():
            # No cache-buster in this URL (unlike static_v() assets), so this must
            # NOT get the /static route's year-long max-age (final-review fix) --
            # a changed avatar has to show up immediately. max_age=0 + no-cache
            # still lets the browser revalidate via the file's ETag/Last-Modified.
            resp = send_from_directory(avatars_dir, filename, max_age=0)
            resp.headers["Cache-Control"] = "no-cache, private"
            return resp
    abort(404)
    return None


def change_password():
    conn = None
    cursor = None
    try:
        if "username" not in session:
            return redirect(url_for("login"))

        if request.method == "POST":
            username = session["username"]
            userid = session["userid"]  # noqa: F841 (kept for parity)

            current_password = request.form["currentPassword"]
            new_password = request.form["newPassword"]
            confirm_password = request.form["confirmPassword"]

            if new_password != confirm_password:
                flash(_("New passwords do not match"), "failure_changePW")
                return redirect(url_for("profile"))
            if not new_password or not confirm_password or not current_password:
                flash(_("All fields must be filled"), "failure_changePW")
                return redirect(url_for("profile"))
            if not re.search(r"^\S{12,200}$", new_password):
                flash(
                    _("New password has to be at least 12 characters long, with no whitespaces"),
                    "failure_changePW",
                )
                return redirect(url_for("profile"))
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT password FROM Users WHERE username = ?", username)
            row = cursor.fetchone()
            if row is None:
                flash(_("Unexpected Error"), "failure_changePW")
                return redirect(url_for("profile"))
            stored_hash = row[0]

            if isinstance(stored_hash, str):
                stored_hash = stored_hash.encode("utf-8")

            if bcrypt.checkpw(current_password.encode("utf-8"), stored_hash):
                salt = bcrypt.gensalt()
                hash_bytes = bcrypt.hashpw(new_password.encode("utf-8"), salt)
                hash_str = hash_bytes.decode("utf-8")

                cursor.execute(
                    """
                    UPDATE Users
                    SET password = ?
                    WHERE username = ?
                    """,
                    (hash_str, username),
                )

                conn.commit()

                flash(_("Password updated successfully!"), "success_changePW")
                return redirect(url_for("profile"))
            flash(_("Current password is incorrect"), "failure_changePW")
            return redirect(url_for("profile"))

        return redirect(url_for("profile"))
    except Exception:
        flash(_("Unexpected Error"), "failure_changePW")
        return redirect(url_for("profile"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def set_language(lang=None):
    conn = None
    try:
        if lang not in ["de", "en", "fr", "it"]:
            flash(_("Unexpected Error"), "failure_setLanguage")
            return redirect(url_for("profile"))
        userid = session["userid"]
        session["locale"] = lang
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET locale = ? WHERE userid = ?", [lang, userid])
        conn.commit()
        cursor.close()
        flash(_("Language changed successfully!"), "success_setLanguage")
        return redirect(url_for("profile"))
    except Exception as e:
        current_app.logger.error(f"set_language error: {e}")
        flash(_("Unexpected Error"), "failure_setLanguage")
        return redirect(url_for("profile"))
    finally:
        if conn:
            conn.close()


def appearance():
    """Standalone appearance-settings page (linked from the profile)."""
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template(
            "appearance.html",
            userid=session.get("userid", "Unknown"),
            logged_in_user=session.get("username", "Unknown"),
            page_visibility=page_visibility(),
        )
    except Exception:
        return render_template("500.html")


def whats_new():
    """Curated per-release notes, filtered to what this user can actually use.
    Opening the page stamps the seen-marker, clearing the header badge."""
    try:
        if "username" not in session:
            return redirect(url_for("login"))
        releases = visible_releases(has_permission)
        mark_seen(session["userid"])
        return render_template(
            "whats_new.html",
            releases=releases,
            userid=session.get("userid", "Unknown"),
            logged_in_user=session.get("username", "Unknown"),
            page_visibility=page_visibility(),
        )
    except Exception:
        return render_template("500.html")


def set_ui_prefs():
    """AJAX endpoint: merge a partial prefs patch into the stored UI prefs."""
    if "userid" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    patch = sanitize_ui_prefs(request.get_json(silent=True))
    if not patch:
        return jsonify({"error": "No valid preferences in request"}), 400
    prefs = dict(session.get("ui_prefs") or {})
    prefs.update(patch)
    if not save_ui_prefs(session["userid"], prefs):
        return jsonify({"error": "Could not save preferences"}), 500
    session["ui_prefs"] = prefs
    return jsonify({"ok": True, "prefs": prefs})


FEEDBACK_CATEGORIES = ("bug", "idea", "question")
FEEDBACK_MAX_MESSAGE_LEN = 5000
FEEDBACK_MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
FEEDBACK_SCREENSHOT_EXTS = {"png", "jpg", "jpeg"}


def feedback():
    """Small in-app "report a problem / suggest something" form. Available to
    every authenticated user, same as Appearance/What's New -- no dedicated
    permission code, so (like those two) it's absent from page_visibility()."""
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template(
        "feedback.html",
        userid=session.get("userid", "Unknown"),
        logged_in_user=session.get("username", "Unknown"),
        from_page=request.args.get("from", ""),
        page_visibility=page_visibility(),
    )


@limiter.limit("10 per hour")
def submit_feedback():
    """AJAX endpoint behind the Feedback page. Mails SUPPORT_MAIL (the
    outage-monitor env var, issue #166) via the existing Graph sender --
    no ticket tracking in-app, the mailbox is the queue (deliberate scope
    cut)."""
    if "username" not in session:
        return jsonify({"error": _("Unauthorized")}), 401

    category = (request.form.get("category") or "").strip().lower()
    message = (request.form.get("message") or "").strip()
    from_page = (request.form.get("from_page") or "").strip()[:200]

    if category not in FEEDBACK_CATEGORIES:
        return jsonify({"error": _("Please choose a category.")}), 400
    if not message:
        return jsonify({"error": _("Please describe the problem or idea.")}), 400
    if len(message) > FEEDBACK_MAX_MESSAGE_LEN:
        return jsonify({"error": _("Message is too long.")}), 400

    attachments = None
    screenshot = request.files.get("screenshot")
    if screenshot and screenshot.filename:
        ext = screenshot.filename.rsplit(".", 1)[-1].lower() if "." in screenshot.filename else ""
        # FEEDBACK_SCREENSHOT_EXTS narrows is_file_allowed's own table (which
        # also accepts pdf/xlsx, not wanted for a screenshot) -- the ext
        # check short-circuits before it, so a non-image never touches the
        # stream at all.
        if ext not in FEEDBACK_SCREENSHOT_EXTS or not is_file_allowed(
            screenshot.filename, screenshot.stream
        ):
            return jsonify({"error": _("Screenshot must be a PNG or JPEG image.")}), 400
        data = screenshot.stream.read()
        if len(data) > FEEDBACK_MAX_SCREENSHOT_BYTES:
            return jsonify({"error": _("Screenshot is too large (max 5 MB).")}), 400
        content_type = "image/png" if ext == "png" else "image/jpeg"
        attachment_name = secure_filename(screenshot.filename) or "screenshot.png"
        attachments = [(attachment_name, data, content_type)]

    if not SUPPORT_MAIL:
        current_app.logger.warning("Feedback submitted but SUPPORT_MAIL is unset -- not mailing.")
        return jsonify({"error": _("Feedback is not configured on this environment.")}), 503

    category_labels = {"bug": _("Bug"), "idea": _("Idea"), "question": _("Question")}
    category_label = category_labels.get(category, category)
    fullname = session.get("fullname") or session.get("username") or "Unknown"
    username = session.get("username", "Unknown")
    environment = os.environ.get("ENVIRONMENT", "?")
    version_str = f"{__version__} ({BUILD_STAMP})" if BUILD_STAMP else __version__

    subject = f"[nexora Feedback] {category_label} — {username}"
    html_body = f"""
    <p><strong>{escape(category_label)}</strong> from
    <strong>{escape(fullname)}</strong> ({escape(username)})</p>
    <p style="white-space: pre-wrap;">{escape(message)}</p>
    <hr>
    <p style="color:#666; font-size:12px;">
      Page: {escape(from_page or "-")}<br>
      Version: {escape(version_str)} &middot; Environment: {escape(environment)}
    </p>
    """

    try:
        send_mail(SUPPORT_MAIL, subject, html_body, attachments=attachments)
    except MailError as e:
        current_app.logger.error(f"Feedback mail failed: {e}")
        return jsonify({"error": _("Could not send feedback. Please try again later.")}), 502

    return jsonify({"ok": True})


def register_routes(app):
    app.add_url_rule("/profile", endpoint="profile", view_func=profile)
    app.add_url_rule(
        "/update_profile",
        endpoint="update_profile",
        view_func=update_profile,
        methods=["POST", "GET"],
    )
    app.add_url_rule(
        "/change_password",
        endpoint="change_password",
        view_func=change_password,
        methods=["POST", "GET"],
    )
    app.add_url_rule("/language/<lang>", endpoint="set_language", view_func=set_language)
    app.add_url_rule(
        "/avatar/<int:user_id>",
        endpoint="user_avatar",
        view_func=user_avatar,
    )
    app.add_url_rule("/appearance", endpoint="appearance", view_func=appearance)
    app.add_url_rule("/whats_new", endpoint="whats_new", view_func=whats_new)
    app.add_url_rule(
        "/profile/ui_prefs",
        endpoint="set_ui_prefs",
        view_func=set_ui_prefs,
        methods=["POST"],
    )
    app.add_url_rule("/feedback", endpoint="feedback", view_func=feedback)
    app.add_url_rule(
        "/feedback/submit",
        endpoint="submit_feedback",
        view_func=submit_feedback,
        methods=["POST"],
    )
