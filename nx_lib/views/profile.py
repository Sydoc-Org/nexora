"""Profile, password change, language switch."""

import io
import os
import re

import bcrypt
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from PIL import Image

from ..db import engineNexoraDB
from ..files import is_file_allowed
from ..security import pageVisability


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
            pageV=pageVisability(),
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
            fullname = request.form["fullName"]
            email = request.form["email"]

            conn = engineNexoraDB.raw_connection()
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
                    rel_path = os.path.join("static", "images", filename)
                    abs_path = os.path.join(current_app.root_path, rel_path)
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
    except Exception:
        flash(_("Unexpected error"), "failure_updateProfile")
        return redirect(url_for("profile"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
            if not re.search(r"^\S{8,200}$", new_password):
                flash(
                    _("New password has to be atleast 8 characters long, with no whitespaces"),
                    "failure_changePW",
                )
                return redirect(url_for("profile"))
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT password FROM Users WHERE username = ?", username)
            row = cursor.fetchone()
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
            else:
                flash(_("Current password is incorrect"), "failure_changePW")
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
        conn = engineNexoraDB.raw_connection()
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
