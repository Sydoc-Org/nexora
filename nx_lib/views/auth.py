"""Authentication, 2FA, and password-reset routes.

Endpoint names are preserved verbatim (``url_for("login")``, ``url_for("logout")``,
etc.) by registering rules with explicit ``endpoint=`` rather than via Blueprint.
"""

import base64
import io
import re
import uuid

import bcrypt
import pyotp
import qrcode
import requests
from flask import (
    abort, current_app, flash, redirect, render_template, request, session, url_for,
)
from flask_babel import gettext as _

from ..config import (
    GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_PASSWORD, GRAPH_TENANT_ID,
    GRAPH_USERNAME, IS_PROD,
)
from ..db import engineNexoraDB
from ..extensions import limiter, s
from ..hooks import get_ip
from ..maintenance import _maintenance_blocks_user
from ..security import (
    _revoke_session_by_id, load_permissions_for_user, pageVisability,
    startpage_redirect_to,
)


def _record_active_session(user_id):
    """Insert the current session's SID into ActiveSessions for admin force-logout.
    No-op on failure - session tracking is non-critical to login success."""
    try:
        import uuid as _uuid
        sid = getattr(session, "sid", None)
        if not sid:
            # Dev fallback (signed-cookie sessions have no server-side SID):
            # generate and stash one so admin UI can still reference it.
            sid = session.get("_dev_sid") or _uuid.uuid4().hex
            session["_dev_sid"] = sid
        ip = (get_ip() or "")[:45]
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        # Upsert: a re-login with the same SID should refresh the row, not collide on PK.
        cursor.execute("DELETE FROM ActiveSessions WHERE SessionID = ?", (str(sid),))
        try:
            cursor.execute(
                "INSERT INTO ActiveSessions (SessionID, UserID, IPAddress) VALUES (?, ?, ?)",
                (str(sid), int(user_id), ip or None),
            )
        except Exception:
            # Fallback when the IPAddress column hasn't been added yet
            # (Patch-ActiveSessions_addIPAddress.sql not applied).
            cursor.execute(
                "INSERT INTO ActiveSessions (SessionID, UserID) VALUES (?, ?)",
                (str(sid), int(user_id)),
            )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        current_app.logger.warning(
            f"Failed to record active session for user {user_id}: {e}"
        )


def send_reset_email(email):
    def get_link():
        token = s.dumps(email, salt="password-reset-salt")
        return url_for("reset_password", token=token, _external=True)

    def get_access_token():
        uri = f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = {
            "client_id": GRAPH_CLIENT_ID,
            "username": GRAPH_USERNAME,
            "password": GRAPH_PASSWORD,
            "grant_type": "password",
            "scope": "Mail.Send",
            "client_secret": GRAPH_CLIENT_SECRET,
        }
        try:
            response = requests.post(uri, headers=headers, data=body, timeout=10)
            return response.json()["access_token"]
        except Exception as e:
            print(e)

    uri = "https://graph.microsoft.com/v1.0/me/sendMail"
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    link = get_link()
    try:
        FONT_FAMILY = "font-family: 'Inter', Helvetica, Arial, sans-serif;"
        CONTAINER_STYLE = "max-width: 600px; margin: 0 auto; background-color: #fefdfb; padding: 20px;"
        BUTTON_STYLE = (
            "background-color: #2563eb; color: #fefdfb; padding: 12px 24px; "
            "text-decoration: none; border-radius: 8px; font-weight: bold; "
            "display: inline-block; mso-padding-alt: 12px 24px;"
        )
        LINK_STYLE = "color: #4b5563; text-decoration: none; margin-right: 15px; font-size: 14px;"
        TEXT_STYLE = "color: #4b5563; line-height: 1.6; font-size: 16px;"

        LOGO_URL = "https://nexora.sydoc.ch/nexora/static/images/nexora-logo.gif"
        LOGO_BANNER_URL = "https://nexora.sydoc.ch/nexora/static/images/sydoc-logo-banner.png"

        body = {
            "message": {
                "subject": _("nexora Password Reset Request"),
                "body": {
                    "contentType": "HTML",
                    "content": f"""
                            <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Nexora Update</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f3f4f6; {FONT_FAMILY}">

        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f3f4f6; padding: 20px;">
            <tr>
                <td align="center">

                    <table width="600" border="0" cellspacing="0" cellpadding="0" style="{CONTAINER_STYLE} border-radius: 8px;">

                        <tr>
                            <td align="center" style="padding-bottom: 20px;">
                                <a href="https://sydoc.ch"><img src="{LOGO_URL}" alt="Sydoc Logo" width="600" style="display: block;"></a>
                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="padding-bottom: 60px;">
                                <a href="https://sydoc.ch/ueber-sydoc/news/" style="{LINK_STYLE}">News</a>
                                <a href="https://sydoc.ch/ueber-sydoc/kundenmagazin/" style="{LINK_STYLE}">Magazin</a>
                                <a href="https://sydoc.ch/ueber-sydoc/team/" style="{LINK_STYLE}">Team</a>
                                <a href="mailto:support.helpdesk@sydoc.ch" style="{LINK_STYLE}">Support</a>
                            </td>
                        </tr>

                        <tr>
                            <td style="padding: 0 10px;">
                                <h2 style="color: #374151; margin-top: 0;">{_("Hello,")}</h2>
                                <p style="{TEXT_STYLE}">
                                    {_("We received a request to reset the password for your account. You can reset your password by clicking the button below.")}
                                   {_("If you did not request a password reset, please ignore this email. This link is valid for 15 minutes.")}
                                </p>
                                <p style="{TEXT_STYLE}">
                                    {_("Thanks,<br>The Sydoc Team")}
                                </p>
                            </td>
                        </tr>

                        <tr>
                            <td align="left" style="padding: 10px 10px 30px;">
                                <a href="{link}" style="{BUTTON_STYLE}">
                                    {_("Reset Your Password")}
                                </a>
                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="padding-top: 30px; border-top: 1px solid #e5e7eb;">
                                <a href="https://sydoc.ch"><img src="{LOGO_BANNER_URL}" alt="Sydoc Logo" width="600" style="display: block;"></a>                            </td>
                        </tr>

                        <tr>
                            <td align="center" style="padding-top: 15px;">
                                <p style="font-size: 12px; color: #9ca3af;">
                                    © 2026 Alle Rechte vorbehalten
                                </p>
                            </td>
                        </tr>

                    </table>

                </td>
            </tr>
        </table>
    </body>
    </html>
                    """,
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}}
                ],
            },
            "saveToSentItems": True,
        }

        response = requests.post(uri, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response body: {response.text}")
        return False
    except Exception as e:
        print(f"An other error occurred: {e}")
        return False


def init_2FA():
    if "pre_2fa_userid" not in session:
        return redirect(url_for("login"))
    user_id = session["pre_2fa_userid"]

    if request.method == "GET":
        secret = pyotp.random_base32()

        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=session.get("pre_2fa_username", "User"),
            issuer_name="nexora",
        )

        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        session["temp_2fa_secret"] = secret
        return render_template("init_2FA.html", qr_code=qr_b64, secret=secret)

    elif request.method == "POST":
        code = request.form.get("code")
        secret = session.get("temp_2fa_secret")

        if not code or not secret:
            flash(_("Session expired, please try again"), "error")
            return redirect(url_for("init_2FA"))

        totp = pyotp.TOTP(secret)
        if totp.verify(code):
            try:
                conn = engineNexoraDB.raw_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    UPDATE Users
                    SET twoFA = 1, TwoFASecret = ?
                    WHERE userid = ?
                    """,
                    (secret, user_id),
                )
                conn.commit()

                cursor.execute(
                    "SELECT username, fullname, email, organizationcode, locale FROM Users WHERE userid = ?",
                    (user_id,),
                )
                row = cursor.fetchone()

                if not row:
                    return redirect(url_for("login"))

                username, fullname, email, org_code, user_locale = row
                session.pop("temp_2fa_secret", None)

                session.clear()
                session["userid"] = user_id
                session["username"] = username
                session["fullname"] = fullname
                session["email"] = email
                session["organizationcode"] = org_code
                session["uuid"] = uuid.uuid4()
                session["permissions"] = load_permissions_for_user(str(user_id))
                _record_active_session(user_id)
                if user_locale in ["de", "en", "fr", "it"]:
                    session["locale"] = user_locale
                pV = pageVisability()
                return redirect(url_for(startpage_redirect_to(pV)))
            except Exception as e:
                current_app.logger.error(f"2FA Setup DB Error: {e}")
                return render_template("init_2FA.html", error=_("Database error"))
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

        else:
            flash(_("Invalid code. Please try again."), "error")
            return redirect(url_for("init_2FA"))


def verify_2fa():
    if "pre_2fa_userid" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("verify_2fa.html")

    elif request.method == "POST":
        code = request.form.get("code")
        user_id = session["pre_2fa_userid"]

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TwoFASecret, username, fullname, email, organizationcode, locale FROM Users WHERE userid = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return redirect(url_for("login"))

        secret, username, fullname, email, org_code, user_locale = row

        totp = pyotp.TOTP(secret)
        if totp.verify(code):
            session.clear()
            session["userid"] = user_id
            session["username"] = username
            session["fullname"] = fullname
            session["email"] = email
            session["organizationcode"] = org_code
            session["uuid"] = uuid.uuid4()
            session["permissions"] = load_permissions_for_user(str(user_id))
            _record_active_session(user_id)
            if user_locale in ["de", "en", "fr", "it"]:
                session["locale"] = user_locale
            pV = pageVisability()
            return redirect(url_for(startpage_redirect_to(pV)))
        else:
            flash(_("Invalid code"), "error")
            return render_template("verify_2fa.html"), 401


def init_reset():
    return render_template("init_reset.html")


def init_reset_password():
    try:
        new_password = request.form["new-password"]
        confirm_password = request.form["confirm-password"]
        pre_auth_userid = session.get("pre_auth_userid")
        if new_password != confirm_password:
            return render_template("init_reset.html", error=_("Passwords do not match"))
        if not new_password or not confirm_password:
            return render_template("init_reset.html", error=_("All Fields must be filled"))
        if not re.search(r"^\S{8,200}$", new_password):
            return render_template("init_reset.html", error=_("New password has to be atleast 8 characters long, with no whitespaces"))

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password, twoFA, username FROM Users WHERE userid = ?",
            pre_auth_userid,
        )
        row = cursor.fetchone()
        stored_hash = row[0]
        stored_2FA = row[1]
        stored_username = row[2]

        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        if bcrypt.checkpw(new_password.encode("utf-8"), stored_hash):
            return render_template("init_reset.html", error=_("New Password musn't be previously used password"))

        salt = bcrypt.gensalt()
        hash_bytes = bcrypt.hashpw(new_password.encode("utf-8"), salt)
        hash_str = hash_bytes.decode("utf-8")

        cursor.execute(
            """
            UPDATE Users
            SET password = ?, initReset = 1
            WHERE userid = ?
            """,
            (hash_str, pre_auth_userid),
        )

        conn.commit()
        cursor.close()
        conn.close()

        if not stored_2FA:
            session["pre_2fa_userid"] = pre_auth_userid
            session["pre_2fa_username"] = stored_username
            return redirect(url_for("init_2FA"))
        return redirect(url_for("login"))
    except Exception:
        return


def dev_login(username):
    if IS_PROD:
        abort(404)
    conn = engineNexoraDB.raw_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT userid, username, fullname, email, organizationcode, locale FROM Users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row:
        abort(404)
    uid, uname, fullname, email, org_code, locale = row
    session.clear()
    session["userid"] = str(uid)
    session["username"] = uname
    session["fullname"] = fullname
    session["email"] = email
    session["organizationcode"] = org_code
    session["uuid"] = uuid.uuid4()
    session["locale"] = locale
    session["permissions"] = load_permissions_for_user(str(uid))
    _record_active_session(str(uid))
    pV = pageVisability()
    return redirect(url_for(startpage_redirect_to(pV)))


@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        if not UID_REQUEST or not PWD_REQUEST:
            return render_template("index.html", error=_("Invalid credentials")), 401

        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT userid, password, username, initreset, twoFA FROM Users WHERE username = ?",
                (UID_REQUEST,),
            )
            user_record = cursor.fetchone()

            if user_record:
                stored_userid = user_record[0]
                stored_hash = user_record[1]
                stored_username = user_record[2]
                stored_initReset = user_record[3]
                stored_2FA = user_record[4]

                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode("utf-8")

                if bcrypt.checkpw(PWD_REQUEST.encode("utf-8"), stored_hash):
                    blocking = _maintenance_blocks_user(stored_userid)
                    if blocking:
                        return render_template("maintenance.html", maintenance=blocking), 503
                    if not stored_initReset:
                        session["pre_auth_userid"] = str(stored_userid)
                        return redirect(url_for("init_reset"))
                    if not stored_2FA:
                        session["pre_2fa_userid"] = str(stored_userid)
                        session["pre_2fa_username"] = stored_username
                        return redirect(url_for("init_2FA"))
                    else:
                        session.clear()
                        session["pre_2fa_userid"] = str(stored_userid)
                        session["pre_2fa_username"] = stored_username
                        return redirect(url_for("verify_2fa"))

            return render_template("index.html", error=_("Invalid credentials")), 401

        except Exception as e:
            current_app.logger.error(f"Database error during login: {e}")
            return render_template("index.html", error=_("Login temporarily unavailable")), 503
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("index.html")


def logout():
    try:
        sid = getattr(session, "sid", None) or session.get("_dev_sid")
        if sid:
            try:
                _revoke_session_by_id(sid)
            except Exception as e:
                current_app.logger.warning(
                    f"Logout: could not delete ActiveSessions row for {sid}: {e}"
                )
        session.pop("username", None)
        session.pop("uuid", None)
        session.pop("userid", None)
        return redirect(url_for("index"))
    except Exception:
        return render_template("500.html")


def forgot_password():
    return render_template("forgot_password.html")


def set_new_password():
    conn = None
    cursor = None
    try:
        email_for_password_reset = session["email_for_password_reset"]
        new_password = request.form["new-password"]
        confirm_password = request.form["confirm-password"]
        if new_password != confirm_password:
            return render_template("reset_password.html", error=_("Passwords do not match"))
        if not new_password or not confirm_password:
            return render_template("reset_password.html", error=_("All Fields must be filled"))
        if not re.search(r"^\S{8,200}$", new_password):
            return render_template("reset_password.html", error=_("New password has to be atleast 8 characters long, with no whitespaces"))

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password, userid FROM Users WHERE Email = ?",
            email_for_password_reset,
        )
        row = cursor.fetchone()
        stored_hash = row[0]

        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        if bcrypt.checkpw(new_password.encode("utf-8"), stored_hash):
            return render_template("reset_password.html", error=_("New Password musn't be previously used password"))

        salt = bcrypt.gensalt()
        hash_bytes = bcrypt.hashpw(new_password.encode("utf-8"), salt)
        hash_str = hash_bytes.decode("utf-8")

        cursor.execute(
            """
            UPDATE Users
            SET password = ?
            WHERE email = ?
            """,
            (hash_str, email_for_password_reset),
        )
        conn.commit()

        return render_template("reset_password.html", message=_("Password changed"))
    except Exception:
        return
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def reset_password(token):
    try:
        session["email_for_password_reset"] = s.loads(
            token, salt="password-reset-salt", max_age=900
        )
        return render_template("reset_password.html")
    except Exception:
        return redirect(url_for("index"))


@limiter.limit("5 per hour")
def request_password_reset():
    conn = None
    cursor = None
    try:
        request_email = request.form["email"]
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE Email = ?", (request_email,))
        rows = cursor.fetchone()

        if rows:
            sendreset = send_reset_email(request_email)
            if sendreset:
                return render_template("forgot_password.html", message=_("A password reset link has been sent to your email"))
            return render_template("forgot_password.html", error=_("Unexpected error occurred"))
        return render_template("forgot_password.html", error=_("Invalid Email Address"))
    except Exception as e:
        print(e)
        return render_template("forgot_password.html", error=_("Unexpected error occurred"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/init_2FA", endpoint="init_2FA", view_func=init_2FA, methods=["GET", "POST"])
    app.add_url_rule("/verify_2fa", endpoint="verify_2fa", view_func=verify_2fa, methods=["GET", "POST"])
    app.add_url_rule("/init_reset", endpoint="init_reset", view_func=init_reset)
    app.add_url_rule("/init_reset_password", endpoint="init_reset_password", view_func=init_reset_password, methods=["POST", "GET"])
    app.add_url_rule("/dev/login/<username>", endpoint="dev_login", view_func=dev_login)
    app.add_url_rule("/login", endpoint="login", view_func=login, methods=["GET", "POST"])
    app.add_url_rule("/logout", endpoint="logout", view_func=logout)
    app.add_url_rule("/forgot_password", endpoint="forgot_password", view_func=forgot_password)
    app.add_url_rule("/set_new_password", endpoint="set_new_password", view_func=set_new_password, methods=["POST", "GET"])
    app.add_url_rule("/reset_password/<token>", endpoint="reset_password", view_func=reset_password)
    app.add_url_rule("/request-password-reset", endpoint="request_password_reset", view_func=request_password_reset, methods=["GET", "POST"])
