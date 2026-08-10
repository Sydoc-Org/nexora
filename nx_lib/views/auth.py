"""Authentication, 2FA, and password-reset routes.

Endpoint names are preserved verbatim (``url_for("login")``, ``url_for("logout")``,
etc.) by registering rules with explicit ``endpoint=`` rather than via Blueprint.
"""

import base64
import hashlib
import io
import re
import threading
import uuid
from datetime import datetime

import bcrypt
import pyotp
import qrcode
import requests
from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _

from ..config import (
    GRAPH_CLIENT_ID,
    GRAPH_CLIENT_SECRET,
    GRAPH_PASSWORD,
    GRAPH_TENANT_ID,
    GRAPH_USERNAME,
    IS_PROD,
)
from ..db import engine_nexora_db
from ..extensions import cache, limiter, s
from ..hooks import get_ip
from ..maintenance import _maintenance_blocks_user
from ..security import (
    _revoke_session_by_id,
    load_permissions_for_user,
    page_visibility,
    startpage_redirect_to,
)


def _record_active_session(user_id):
    """Insert the current session's SID into ActiveSessions for admin force-logout.
    No-op on failure - session tracking is non-critical to login success."""
    # Stamped on every login path; the dashboard shows it once (issue #146).
    session["login_at"] = datetime.now()
    session["show_login_note"] = True
    try:
        import uuid as _uuid

        sid = getattr(session, "sid", None)
        if not sid:
            # Dev fallback (signed-cookie sessions have no server-side SID):
            # generate and stash one so admin UI can still reference it.
            sid = session.get("_dev_sid") or _uuid.uuid4().hex
            session["_dev_sid"] = sid
        ip = (get_ip() or "")[:45]
        conn = engine_nexora_db.raw_connection()
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
        # Previous login stamp, read before it is overwritten (issue #146).
        cursor.execute("SELECT LastLoginAt FROM Users WHERE userID = ?", (int(user_id),))
        row = cursor.fetchone()
        session["prev_login_at"] = row[0] if row else None
        cursor.execute("UPDATE Users SET LastLoginAt = GETDATE() WHERE userID = ?", (int(user_id),))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        current_app.logger.warning(f"Failed to record active session for user {user_id}: {e}")


def _build_reset_email_message(email, invite=False):
    """Build the Graph sendMail payload (reset link + translated subject/
    body) for a password-reset email to ``email``.

    With ``invite=True`` the same markup carries the welcome copy sent when
    an admin creates a user with "email a set-password link" ticked -- the
    link is minted from the longer-lived invite salt (an onboarding mail may
    sit unread for days; a 15-minute reset link would be dead on arrival).

    Uses ``url_for(_external=True)`` and gettext (``_()``), both bound to
    the live Flask request/app context. Call this synchronously, before
    send_reset_email() is dispatched onto a background thread -- request/g/
    current_app are not valid once the triggering request has returned.
    """

    def get_link():
        salt = "user-invite-salt" if invite else "password-reset-salt"
        return url_for("reset_password", token=s.dumps(email, salt=salt), _external=True)

    link = get_link()
    if invite:
        subject = _("Your nexora account is ready")
        intro = _(
            "An account has been created for you on nexora. Choose your own password by "
            "clicking the button below. You will then be asked to set up two-factor "
            "authentication."
        )
        validity = _("This link is valid for 7 days.")
        button_label = _("Set Your Password")
    else:
        subject = _("nexora Password Reset Request")
        intro = _(
            "We received a request to reset the password for your account. You can reset "
            "your password by clicking the button below."
        )
        validity = _(
            "If you did not request a password reset, please ignore this email. This link "
            "is valid for 15 minutes."
        )
        button_label = _("Reset Your Password")
    font_family = "font-family: 'Inter', Helvetica, Arial, sans-serif;"
    container_style = "max-width: 600px; margin: 0 auto; background-color: #fefdfb; padding: 20px;"
    button_style = (
        "background-color: #2563eb; color: #fefdfb; padding: 12px 24px; "
        "text-decoration: none; border-radius: 8px; font-weight: bold; "
        "display: inline-block; mso-padding-alt: 12px 24px;"
    )
    link_style = "color: #4b5563; text-decoration: none; margin-right: 15px; font-size: 14px;"
    text_style = "color: #4b5563; line-height: 1.6; font-size: 16px;"

    logo_url = "https://nexora.sydoc.ch/nexora/static/images/nexora-logo.gif"
    logo_banner_url = "https://nexora.sydoc.ch/nexora/static/images/sydoc-logo-banner.png"

    body = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": f"""
                        <!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Nexora Update</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; {font_family}">

    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f3f4f6; padding: 20px;">
        <tr>
            <td align="center">

                <table width="600" border="0" cellspacing="0" cellpadding="0" style="{container_style} border-radius: 8px;">

                    <tr>
                        <td align="center" style="padding-bottom: 20px;">
                            <a href="https://sydoc.ch"><img src="{logo_url}" alt="Sydoc Logo" width="600" style="display: block;"></a>
                        </td>
                    </tr>

                    <tr>
                        <td align="center" style="padding-bottom: 60px;">
                            <a href="https://sydoc.ch/ueber-sydoc/news/" style="{link_style}">News</a>
                            <a href="https://sydoc.ch/ueber-sydoc/kundenmagazin/" style="{link_style}">Magazin</a>
                            <a href="https://sydoc.ch/ueber-sydoc/team/" style="{link_style}">Team</a>
                            <a href="mailto:support.helpdesk@sydoc.ch" style="{link_style}">Support</a>
                        </td>
                    </tr>

                    <tr>
                        <td style="padding: 0 10px;">
                            <h2 style="color: #374151; margin-top: 0;">{_("Hello,")}</h2>
                            <p style="{text_style}">
                                {intro}
                               {validity}
                            </p>
                            <p style="{text_style}">
                                {_("Thanks,<br>The Sydoc Team")}
                            </p>
                        </td>
                    </tr>

                    <tr>
                        <td align="left" style="padding: 10px 10px 30px;">
                            <a href="{link}" style="{button_style}">
                                {button_label}
                            </a>
                        </td>
                    </tr>

                    <tr>
                        <td align="center" style="padding-top: 30px; border-top: 1px solid #e5e7eb;">
                            <a href="https://sydoc.ch"><img src="{logo_banner_url}" alt="Sydoc Logo" width="600" style="display: block;"></a>                            </td>
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
            "toRecipients": [{"emailAddress": {"address": email}}],
        },
        "saveToSentItems": True,
    }
    return body


def send_reset_email(email, message=None):
    """Send a password-reset email via Microsoft Graph.

    D-RESET: request_password_reset() dispatches this call on a daemon
    thread so a registered address does not take measurably longer to
    answer than an unregistered one (the previous timing oracle). Pass a
    pre-built ``message`` (see _build_reset_email_message) so nothing here
    touches Flask request/app context -- only plain data and network I/O,
    which is safe to run off the request thread.
    """
    if message is None:
        message = _build_reset_email_message(email)

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
    try:
        response = requests.post(uri, headers=headers, json=message, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response body: {response.text}")
        return False
    except Exception as e:
        print(f"An other error occurred: {e}")
        return False


@limiter.limit("30 per hour")
def init_2fa():
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
        # valid_window=1 also accepts the adjacent 30s windows. Guards against
        # client/server clock skew and the window rolling over between code
        # generation and verification (the latter flakes E2E tests hard).
        if totp.verify(code, valid_window=1):
            conn = None
            cursor = None
            try:
                conn = engine_nexora_db.raw_connection()
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
                page_v = page_visibility()
                return redirect(url_for(startpage_redirect_to(page_v)))
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


@limiter.limit("30 per hour")
def verify_2fa():
    if "pre_2fa_userid" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("verify_2fa.html")

    elif request.method == "POST":
        code = request.form.get("code")
        user_id = session["pre_2fa_userid"]

        conn = engine_nexora_db.raw_connection()
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
        # valid_window=1 also accepts the adjacent 30s windows (clock skew /
        # window roll-over between code generation and verification).
        if totp.verify(code, valid_window=1):
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
            page_v = page_visibility()
            return redirect(url_for(startpage_redirect_to(page_v)))
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
            return render_template(
                "init_reset.html",
                error=_("New password has to be atleast 8 characters long, with no whitespaces"),
            )

        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT password, twoFA, username FROM Users WHERE userid = ?",
            pre_auth_userid,
        )
        row = cursor.fetchone()
        stored_hash = row[0]
        stored_2fa = row[1]
        stored_username = row[2]

        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode("utf-8")

        if bcrypt.checkpw(new_password.encode("utf-8"), stored_hash):
            return render_template(
                "init_reset.html", error=_("New Password musn't be previously used password")
            )

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

        if not stored_2fa:
            session["pre_2fa_userid"] = pre_auth_userid
            session["pre_2fa_username"] = stored_username
            return redirect(url_for("init_2FA"))
        return redirect(url_for("login"))
    except Exception as e:
        current_app.logger.error(f"Password reset (init) failed: {e}")
        # Task 41 originally flash()ed this and redirected to /login, but
        # index.html (the login template) never renders flashed messages --
        # the user saw nothing here and the message resurfaced later on an
        # unrelated page that does render flashes. login()'s own error path
        # uses render_template("index.html", error=...); match that idiom so
        # the message is visible on the page the user actually lands on.
        return render_template("index.html", error=_("Something went wrong, please try again"))


# Fixed dummy hash so login() pays the bcrypt cost even when the username
# doesn't exist -- otherwise response latency reveals which usernames are real
# (username enumeration, #193). Computed once at import at bcrypt's default
# cost so it tracks the cost of real stored hashes.
_DUMMY_BCRYPT_HASH = bcrypt.hashpw(b"nexora-login-timing-equalizer", bcrypt.gensalt())


def _dev_route_forbidden():
    """Guard for the passwordless /dev/* routes. 404 on PROD, and 404 for any
    non-loopback caller on non-PROD, so a network-reachable INT/STAGING/TEST
    instance (e.g. fronted by the SYAPP01 ngrok tunnel) can't use these as a
    remote password+2FA bypass (#193). remote_addr is the real socket peer
    (not the spoofable X-Forwarded-For), so local `nx --loginas` on 127.0.0.1
    still works while remote callers are refused."""
    if IS_PROD:
        return True
    return request.remote_addr not in ("127.0.0.1", "::1")


def dev_login(username):
    if _dev_route_forbidden():
        abort(404)
    conn = engine_nexora_db.raw_connection()
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
    nxt = request.args.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    page_v = page_visibility()
    return redirect(url_for(startpage_redirect_to(page_v)))


def dev_users():
    if _dev_route_forbidden():
        abort(404)
    conn = engine_nexora_db.raw_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM Users WHERE username IS NOT NULL ORDER BY username")
        usernames = [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()
    return jsonify(usernames)


@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        username_request = request.form["username"]
        password_request = request.form["password"]
        if not username_request or not password_request:
            return render_template("index.html", error=_("Invalid credentials")), 401

        conn = None
        cursor = None
        try:
            conn = engine_nexora_db.raw_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT userid, password, username, initreset, twoFA FROM Users WHERE username = ?",
                (username_request,),
            )
            user_record = cursor.fetchone()

            if user_record:
                stored_userid = user_record[0]
                stored_hash = user_record[1]
                stored_username = user_record[2]
                stored_init_reset = user_record[3]
                stored_2fa = user_record[4]

                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode("utf-8")

                if bcrypt.checkpw(password_request.encode("utf-8"), stored_hash):
                    blocking = _maintenance_blocks_user(stored_userid)
                    if blocking:
                        return render_template("maintenance.html", maintenance=blocking), 503
                    if not stored_init_reset:
                        session.clear()
                        session["pre_auth_userid"] = str(stored_userid)
                        return redirect(url_for("init_reset"))
                    if not stored_2fa:
                        session.clear()
                        session["pre_2fa_userid"] = str(stored_userid)
                        session["pre_2fa_username"] = stored_username
                        return redirect(url_for("init_2FA"))
                    else:
                        session.clear()
                        session["pre_2fa_userid"] = str(stored_userid)
                        session["pre_2fa_username"] = stored_username
                        return redirect(url_for("verify_2fa"))
            else:
                # Unknown username: still run one bcrypt comparison against a
                # fixed dummy hash so the response takes the same time as a
                # wrong password for a real account -- latency can't be used to
                # tell valid usernames from invalid ones (#193).
                bcrypt.checkpw(password_request.encode("utf-8"), _DUMMY_BCRYPT_HASH)

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
    if "email_for_password_reset" not in session:
        return redirect(url_for("login"))
    # Phase-10 finding fix: authorizing purely on session membership let a
    # third party who fetched the reset link earlier (mail-gateway prescan,
    # shared inbox, proxy log) retain an unbounded write capability in THEIR
    # OWN session -- even after the legitimate user's own successful write
    # burned the token (338e55f moved consumption here). Also covers a
    # session carrying the capability but predating password_reset_token_key
    # (pre-338e55f), which used to write successfully while silently never
    # marking the token consumed. Check this BEFORE any validation below --
    # if the token is already spent, no other validation result matters.
    key = session.get("password_reset_token_key")
    if not key or cache.get(key):
        session.pop("email_for_password_reset", None)
        session.pop("password_reset_token_key", None)
        return redirect(url_for("login"))
    conn = None
    cursor = None
    try:
        email_for_password_reset = session["email_for_password_reset"]
        new_password = request.form["new-password"]
        confirm_password = request.form["confirm-password"]
        # D-RESET / retry fix: these are validation-error branches (typo'd
        # confirmation, empty fields, too short, password reuse) -- re-render
        # the form with an error and fall straight through WITHOUT popping
        # the session capability below, so the user can correct the mistake
        # and resubmit with the same still-valid token. Only a terminal exit
        # (success, or the except branch's hard failure) pops it.
        if new_password != confirm_password:
            return render_template(_set_password_template(), error=_("Passwords do not match"))
        if not new_password or not confirm_password:
            return render_template(_set_password_template(), error=_("All Fields must be filled"))
        if not re.search(r"^\S{8,200}$", new_password):
            return render_template(
                _set_password_template(),
                error=_("New password has to be atleast 8 characters long, with no whitespaces"),
            )

        conn = engine_nexora_db.raw_connection()
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
            return render_template(
                _set_password_template(), error=_("New Password musn't be previously used password")
            )

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

        # D-RESET: the reset token is only marked single-use-spent -- and the
        # "I may set a new password for this email" session capability only
        # dropped -- on a genuinely successful write. Rendering the GET link
        # (reset_password()) no longer consumes it (a refresh, tab-restore,
        # or a mail-gateway link scanner prefetching the URL must not burn
        # it), and a validation-error retry above leaves both intact too.
        token_cache_key = session.get("password_reset_token_key")
        if token_cache_key:
            cache.set(token_cache_key, True, timeout=INVITE_TOKEN_MAX_AGE)
        session.pop("email_for_password_reset", None)
        session.pop("password_reset_token_key", None)

        return render_template(
            _set_password_template(),
            message=(
                _("Password set. You can now sign in.")
                if session.get("password_set_is_invite")
                else _("Password changed")
            ),
        )
    except Exception as e:
        current_app.logger.error(f"Password reset (set new password) failed: {e}")
        # Terminal failure (DB error, missing/garbled user row, ...) -- not a
        # simple retry-able mistake, so the capability is dropped and the
        # user must request a fresh reset link.
        session.pop("email_for_password_reset", None)
        session.pop("password_reset_token_key", None)
        # Task 41 originally flash()ed this and redirected to /login, but
        # index.html never renders flashed messages -- see the matching note
        # in init_reset_password's except branch above.
        return render_template("index.html", error=_("Something went wrong, please try again"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Must match the max_age passed to s.loads() below.
RESET_TOKEN_MAX_AGE = 900
# Admin-issued welcome links (see _build_reset_email_message(invite=True)) --
# an onboarding mail may sit unread over a weekend, so 15 minutes is useless
# here. Also the TTL of every single-use marker: the marker must outlive the
# longest-lived token it guards, or a spent invite link would go re-usable
# once the marker expired.
INVITE_TOKEN_MAX_AGE = 7 * 24 * 3600


def _load_reset_token(token):
    """Unseal a set-password token, whichever kind it is. -> (email, is_invite)

    Two salts, two lifetimes: self-service reset (15 min) and admin invite
    (7 days). Both are verified signatures -- an expired or forged token
    raises out of here and the caller bounces to /.
    """
    try:
        return s.loads(token, salt="password-reset-salt", max_age=RESET_TOKEN_MAX_AGE), False
    except Exception:
        return s.loads(token, salt="user-invite-salt", max_age=INVITE_TOKEN_MAX_AGE), True


def _set_password_template():
    """Which page the set-a-password form lives on for this visitor.

    An invited user has no previous password, so the reset page's copy ("your
    new password must be different from your previous one", "Reset password")
    is nonsense to them -- they get the welcome page instead. Same form, same
    POST target, same validation; only the wording differs.
    """
    return "set_password.html" if session.get("password_set_is_invite") else "reset_password.html"


def _reset_token_cache_key(token):
    """Cache key for single-use tracking. Hash the raw token rather than
    using it verbatim as a key -- the token is a bearer credential and
    should not be persisted (even in an in-memory cache, even as a dict key
    that could surface in a debugger/log dump) in recoverable form."""
    return "reset-token-used:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def reset_password(token):
    try:
        email, is_invite = _load_reset_token(token)

        # Single-use enforcement: reject a token already spent by a prior
        # SUCCESSFUL password write (set_new_password() is what actually
        # marks the cache key -- see there). Rendering this GET route itself
        # must stay side-effect-free w.r.t. the token: a plain browser
        # refresh/tab-restore/back-forward, or a link-scanning mail gateway
        # (Defender Safe Links, Proofpoint, Mimecast, ...) prefetching the
        # URL before the user ever clicks it, would otherwise burn the link
        # pre-emptively and strand the user with no explanation. NOTE:
        # `cache` (Flask-Caching SimpleCache) is an in-process dict -- under
        # wfastcgi's multi-worker deployment each worker process has its own
        # cache, so a token consumed on worker A is still unseen as "used"
        # by worker B. This makes single-use best-effort ACROSS WORKERS, not
        # perfectly atomic. Accepted per the plan's D-RESET decision -- not
        # a gap to fix further here.
        cache_key = _reset_token_cache_key(token)
        if cache.get(cache_key):
            return redirect(url_for("index"))

        session["email_for_password_reset"] = email
        # Carried through to set_new_password() so a successful write can
        # mark this exact token consumed -- see the cache.set() call there.
        # This is the SHA-256 cache key, not the raw bearer token, so it's
        # safe to persist (matches _reset_token_cache_key()'s non-reversible
        # intent).
        session["password_reset_token_key"] = cache_key
        session["password_set_is_invite"] = is_invite
        return render_template(_set_password_template())
    except Exception:
        return redirect(url_for("index"))


@limiter.limit("5 per hour")
def request_password_reset():
    conn = None
    cursor = None
    try:
        request_email = request.form["email"]
        conn = engine_nexora_db.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE Email = ?", (request_email,))
        rows = cursor.fetchone()

        # D8: always return the same neutral message regardless of whether the
        # email belongs to a registered account — differing responses let a
        # caller enumerate valid accounts. send_reset_email() itself stays
        # gated on the row actually existing, so mail is only ever sent to a
        # real, registered address.
        #
        # D-RESET: the send itself must not be awaited here either — the
        # synchronous Graph mail call used to run only on this branch, so a
        # registered address took measurably longer to answer than an
        # unregistered one (a timing oracle even with the response body now
        # unified). Build the message now, while the request context is
        # still live (send_reset_email()/_build_reset_email_message() use
        # url_for() and gettext(), which need it), then hand the network
        # call off to a daemon thread so both branches return immediately.
        # The thread catches/logs its own exceptions -- nothing may escape
        # unhandled onto a background thread under IIS/wfastcgi -- and it
        # touches no Flask request/app-context object, since those are not
        # valid once this request has returned.
        if rows:
            try:
                reset_message = _build_reset_email_message(request_email)
            except Exception as e:
                reset_message = None
                print(f"Failed to build password reset email: {e}")

            if reset_message is not None:

                def _send_reset_email_background():
                    try:
                        send_reset_email(request_email, message=reset_message)
                    except Exception as e:
                        print(f"Failed to send password reset email: {e}")

                threading.Thread(target=_send_reset_email_background, daemon=True).start()
        return render_template(
            "forgot_password.html",
            message=_("If that email is registered, a reset link has been sent."),
        )
    except Exception as e:
        print(e)
        return render_template("forgot_password.html", error=_("Unexpected error occurred"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def register_routes(app):
    app.add_url_rule("/init_2FA", endpoint="init_2FA", view_func=init_2fa, methods=["GET", "POST"])
    app.add_url_rule(
        "/verify_2fa", endpoint="verify_2fa", view_func=verify_2fa, methods=["GET", "POST"]
    )
    app.add_url_rule("/init_reset", endpoint="init_reset", view_func=init_reset)
    app.add_url_rule(
        "/init_reset_password",
        endpoint="init_reset_password",
        view_func=init_reset_password,
        methods=["POST", "GET"],
    )
    app.add_url_rule("/dev/login/<username>", endpoint="dev_login", view_func=dev_login)
    app.add_url_rule("/dev/users", endpoint="dev_users", view_func=dev_users)
    app.add_url_rule("/login", endpoint="login", view_func=login, methods=["GET", "POST"])
    app.add_url_rule("/logout", endpoint="logout", view_func=logout)
    app.add_url_rule("/forgot_password", endpoint="forgot_password", view_func=forgot_password)
    app.add_url_rule(
        "/set_new_password",
        endpoint="set_new_password",
        view_func=set_new_password,
        methods=["POST", "GET"],
    )
    app.add_url_rule("/reset_password/<token>", endpoint="reset_password", view_func=reset_password)
    app.add_url_rule(
        "/request-password-reset",
        endpoint="request_password_reset",
        view_func=request_password_reset,
        methods=["GET", "POST"],
    )
