import math
import uuid
from fileinput import filename
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, Response, make_response, send_file
from flask_babel import Babel, gettext, ngettext, _
import pyodbc
from pyodbc import DatabaseError
from dotenv import load_dotenv
import os
import bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pathlib import Path
import re
import json
import requests
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import base64
from PIL import Image
import io
from flask_caching import Cache
from datetime import datetime, timedelta
from functools import wraps
import time
from werkzeug.utils import secure_filename

# -------------------------------- app config -------------------------------- #
app = Flask(__name__)
load_dotenv()
# ---------------------------------- locale ---------------------------------- #
def get_locale():
    if 'locale' in session:
        return session['locale']
    user = getattr(g, 'user', None)
    if user is not None and user.locale in ['en', 'de', 'fr', 'it']:
        return user.locale
    return request.accept_languages.best_match(['de', 'fr', 'en', 'it'])

def get_timezone():
    user = getattr(g, 'user', None)
    if user is not None:
        return user.timezone
babel = Babel(app, locale_selector=get_locale, timezone_selector=get_timezone)
# -------------------------------- locale end -------------------------------- #

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True  
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  

DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER_PRD = os.environ.get("DB_SERVER_PRD")
DB_SERVER_DB_WEBPORTAL = os.environ.get("DB_SERVER_DB_WEBPORTAL")
DB_SERVER_DB_STAT = os.environ.get("DB_SERVER_DB_STAT")
DB_SERVER_DB_RUNTIME = os.environ.get("DB_SERVER_DB_RUNTIME")
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
OCTO_CLIENT_SECRET = os.environ.get("OCTO_CLIENT_SECRET")
OCTO_CLIENT_ID = os.environ.get("OCTO_CLIENT_ID")
OCTO_GRANT_TYPE = os.environ.get("OCTO_GRANT_TYPE")

class PrefixMiddleware(object):
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
            environ['SCRIPT_NAME'] = self.prefix
            return self.app(environ, start_response)
        else:
            start_response('404 NOT FOUND', [('Content-Type', 'text/plain')])
            return [b'This URL does not belong to the application.']
# --------------------------------- app start -------------------------------- #
@app.route("/")
def index():
    if 'username' in session:
        return redirect(url_for("dashboard"))
    return render_template("hero.html")
# ------------------------------- app start end ------------------------------ #

# ------------------------------ app config end ------------------------------ #

# ---------------------------------- logging --------------------------------- #
def log_user_action(action_type, status, target_user_id=None, resource_id=None, details=None, IsInternalError=0):
    if 'username' not in session:
        return
    try:
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO User_Logs 
            (SessionID, UserID, Username, PerformerScope, ActionType, ActionStatus, TargetUserID, TargetResourceID, Details, IPAddress, UserAgent, IsInternalError)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get('uuid'),
            session.get('userid'),
            session.get('username'),
            session.get('scope'),
            action_type,
            str(status),
            target_user_id,
            resource_id,
            json.dumps(details) if details else None,
            request.remote_addr,
            request.headers.get('User-Agent', ''),
            IsInternalError
        ))
        
        conn.commit()
    except Exception as e:
        app.logger.error(f"Failed to log user action '{action_type}': {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route("/log_action", methods=['POST'])
def log_action():
    if 'username' not in session:
        return jsonify({'error': 'not authenticated'}), 401
    
    data = request.get_json()
    log_user_action(action_type=(data.get('action_type')),
                    resource_id=(data.get('resource_id')),
                    status=(data.get('status')),
                    details=(data.get('details')),
                    IsInternalError=(data.get('IsInternalError'))
                    )
    
    return jsonify({'success': True})
# -------------------------------- logging end ------------------------------- #

# ------------------------------- session login ------------------------------ #

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        REMEMBER = request.form.getlist('remember')
        if not UID_REQUEST or not PWD_REQUEST:
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"clientError": "Invalid credentials"})
            return render_template('index.html', error=_("Invalid credentials"))

        try:
            conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER_PRD},1433;'
                f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};' 
                f'TrustServerCertificate=yes;'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT userID, password, Scope, username, fullname, email, company, access, Subscription FROM Users WHERE username = ?
            """, (UID_REQUEST,))
            user_record = cursor.fetchone()

            if user_record:
                stored_userid = user_record[0]
                stored_hash = user_record[1]
                scope = user_record[2]
                stored_username = user_record[3]
                stored_fullname = user_record[4]
                stored_email = user_record[5]
                stored_company = user_record[6]
                stored_access = user_record[7]
                stored_subscription = user_record[8]

                
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')    
            
                if bcrypt.checkpw(PWD_REQUEST.encode('utf-8'), stored_hash):
                    session.clear()
                    session['userid'] = str(stored_userid)  
                    session['username'] = stored_username
                    session['fullname'] = stored_fullname
                    session['email'] = stored_email
                    session['scope'] = scope
                    session['company'] = stored_company
                    session['uuid'] = uuid.uuid4()
                    session['access'] = stored_access
                    session['subscription'] = stored_subscription

                    if len(REMEMBER) > 0:
                        session.permanent = True

                    log_user_action(action_type='logUserIn', status='SUCCESS', resource_id='login')
                    return redirect(url_for("dashboard"))
                
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"clientError": "Invalid credentials"})
            return render_template('index.html', error=_("Invalid credentials"))

        except Exception as e:
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"serverError": str(e)}, IsInternalError=1)
            app.logger.error(f"Database error during login: {e}")
            return render_template('index.html', error=_("Login temporarily unavailable"))
        
    return render_template('index.html')
# ----------------------------- session login end ---------------------------- #

# ------------------------------- notifications ------------------------------ #
def create_notification(user_id, message, link=None, icon='fa-info-circle'):
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Notifications (UserID, Message, Link, Icon)
            VALUES (?, ?, ?, ?)
        """, (user_id, message, link, icon))
        conn.commit()
    except Exception as e:
        app.logger.error(f"Failed to create notification for UserID {user_id}: {e}")
    finally:
        if conn:
            conn.close()

@app.route("/api/notifications")
def get_notifications():
    if 'userid' not in session:
        return jsonify({"error": _("Not authenticated")}), 401
    
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT TOP 10 NotificationID, Message, Link, Icon, Timestamp
            FROM Notifications
            WHERE UserID = ? AND IsRead = 0
            ORDER BY Timestamp DESC
        """, (session['userid'],))
        
        notifications = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        return jsonify(notifications)
    except Exception as e:
        app.logger.error(f"API Error fetching notifications: {e}")
        return jsonify({"error": _("Could not fetch notifications")}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/notifications/mark_as_read", methods=['POST'])
def mark_notifications_as_read():
    if 'userid' not in session:
        return jsonify({"error": _("Not authenticated")}), 401
    
    data = request.get_json()
    notification_ids = data.get('ids')

    if not notification_ids or not isinstance(notification_ids, list):
        return jsonify({"error": _("Invalid payload")}), 400

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?' for _ in notification_ids])
        
        query = f"""
            UPDATE Notifications
            SET IsRead = 1
            WHERE UserID = ? AND NotificationID IN ({placeholders})
        """
        
        params = [session['userid']] + notification_ids
        cursor.execute(query, params)
        conn.commit()
        
        return jsonify({"success": True, "message": _("Notifications marked as read.")})
    except Exception as e:
        app.logger.error(f"API Error marking notifications as read: {e}")
        return jsonify({"error": _("Could not update notifications")}), 500
    finally:
        if conn:
            conn.close()
# ----------------------------- notifications end ---------------------------- #

# ----------------------------------- admin ---------------------------------- #
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'scope' not in session or session['scope'] != 'Admin':
            return forbiddenPage(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = None
    try:
        logged_in_user = session.get('username', 'Unknown')
        scope = session.get('scope', 'Unknown')
        userid = session.get('userid', 'Unknown')
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT userID, username, fullname, email, company, scope, access, subscription FROM Users ORDER BY username")
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        log_user_action('visitUserManagement', status='SUCCESS', resource_id='userManagement')
        return render_template("admin/userManagement.html", users=users, logged_in_user=logged_in_user, scope=scope, userid=userid)
    except Exception as e:
        app.logger.error(f"Failed to fetch users for admin panel: {e}")
        log_user_action('visitUserManagement', status='FAILURE', resource_id='userManagement', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            conn.close()

@app.route("/admin/users/add", methods=['POST'])
@admin_required
def admin_add_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    fullname = data.get('fullname')
    email = data.get('email')
    company = data.get('company')
    access = data.get('access')
    subscription = data.get('subscription')
    scope = data.get('scope')
    userid = session['userid']
    if not all([username, password, fullname, email, company, scope, access, subscription]):
        return jsonify({'success': False, 'message': _("All fields are required.")}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Users (username, password, fullname, email, company, scope, access, subscription) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (username, hashed_password, fullname, email, company, scope, access, subscription))
        conn.commit()
        create_notification(userid, _("User created successfully.") , link=url_for('admin_users'), icon='fa-user-plus')
        log_user_action('createNewUserAdmin', status='SUCCESS', resource_id='visitUserManagement',details={'newUsername': username, 'scope': scope})
        return jsonify({'success': True, 'message': _("User created successfully.")})
    except pyodbc.IntegrityError:
        log_user_action('createNewUserAdmin', status='FAILURE', resource_id='visitUserManagement', details={"adminError": "Username or email already exists", 'newUsername': username, 'scope': scope})
        return jsonify({'success': False, 'message': _("Username or email already exists.")}), 409
    except Exception as e:
        app.logger.error(f"Error adding user: {e}")
        log_user_action('createNewUserAdmin', status='FAILURE', resource_id='visitUserManagement', details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route("/admin/users/edit/<int:user_id>", methods=['POST'])
@admin_required
def admin_edit_user(user_id):
    data = request.get_json()
    username = data.get('username')
    fullname = data.get('fullname')
    email = data.get('email')
    company = data.get('company')
    access = data.get('access')
    subscription = data.get('subscription')
    scope = data.get('scope')
    password = data.get('password') 
    currentUserId = session['userid']

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute("UPDATE Users SET username=?, fullname=?, email=?, company=?, scope=?, password=?, access=?, subscription=? WHERE userID=?",
                           (username, fullname, email, company, scope, hashed_password, access, subscription, user_id))
        else:
            cursor.execute("UPDATE Users SET username=?, fullname=?, email=?, company=?, scope=?,access=?,subscription=? WHERE userID=?",
                           (username, fullname, email, company, scope, access, subscription, user_id))
        conn.commit()

        create_notification(currentUserId, _("User updated successfully"), link=url_for('admin_users'), icon='fa-user-pen')
        log_user_action('editUserAdmin', status='SUCCESS', resource_id='visitUserManagement', target_user_id=user_id)
        return jsonify({'success': True, 'message': _("User updated successfully.")})
    except Exception as e:
        app.logger.error(f"Error editing user {user_id}: {e}")
        log_user_action('editUserAdmin', status='FAILURE', resource_id='visitUserManagement', target_user_id=user_id, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route("/admin/users/delete/<int:user_id>", methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    current_user = session.get('userid')
    if str(user_id) == current_user:
        log_user_action('deleteUserAdmin', status='FAILURE', target_user_id=user_id, details={'adminError': 'Self-delete attempt'}, resource_id='visitUserManagement')
        return jsonify({'success': False, 'message': _("You cannot delete your own account.")}), 403

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Users WHERE userID=?", (user_id,))
        conn.commit()

        if cursor.rowcount == 0:
            log_user_action('deleteUserAdmin', status='FAILURE', target_user_id=user_id, details={'adminError': 'User not found'}, resource_id='visitUserManagement')
            return jsonify({'success': False, 'message': _("User not found.")}), 404
        
        create_notification(current_user, _("User deleted successfully"), link=url_for('admin_users'), icon='fa-user-slash')
        log_user_action('deleteUserAdmin', status='SUCCESS', target_user_id=user_id, resource_id='visitUserManagement')
        return jsonify({'success': True, 'message': _("User deleted successfully.")})
    except Exception as e:
        app.logger.error(f"Error deleting user {user_id}: {e}")
        log_user_action('deleteUserAdmin', status='FAILURE', target_user_id=user_id, resource_id='visitUserManagement', details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/admin/recent_logs")
@admin_required
def admin_recent_logs():
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 20 Timestamp, Username, ActionType, ActionStatus
            FROM User_Logs
            ORDER BY Timestamp DESC
        """)
        logs = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(logs)
    except Exception as e:
        app.logger.error(f"Failed to fetch recent logs for admin panel: {e}")
        return jsonify({"error": _("Could not fetch logs")}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/admin/active_sessions")
@admin_required
def admin_active_sessions():
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
				Username,
				Userid,
                IPAddress,
                MAX(Timestamp) as LastActivity
            FROM User_Logs
            WHERE Timestamp >= DATEADD(minute, -30, GETUTCDATE())
            GROUP BY SessionID, Username, IPAddress, Userid
            ORDER BY LastActivity DESC
        """)
        sessions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(sessions)
    except Exception as e:
        app.logger.error(f"Failed to fetch active sessions for admin panel: {e}")
        return jsonify({"error": _("Could not fetch sessions")}), 500
    finally:
        if conn:
            conn.close()
# --------------------------------- admin end -------------------------------- #

# ---------------------------------- logout ---------------------------------- #
@app.route("/logout")
def logout():
    try:
        session.pop('username', None)
        session.pop('uuid', None)
        session.pop('userid', None)
        log_user_action('logUserOut', status='SUCCESS', resource_id='logout')
        return redirect(url_for("index"))
    except Exception as e:
        log_user_action('logUserOut', status='FAILURE', resource_id='logout', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')
# -------------------------------- logout end -------------------------------- #

# ------------------------------ forgot password ----------------------------- #
@app.route('/forgot_password')
def forgot_password():
    return render_template("forgot_password.html")

@app.route('/set_new_password', methods=['POST', 'GET'])
def set_new_password():
    try:
        email_for_password_reset = session['email_for_password_reset']
        new_password = request.form['new-password']
        confirm_password = request.form['confirm-password']
        if new_password != confirm_password:
            return render_template("reset_password.html", error=_("Passwords do not match"))
        if not new_password or not confirm_password:
            return render_template("reset_password.html", error=_("All Fields must be filled"))
        if not re.search('^\S{8,200}$', new_password):
            return render_template("reset_password.html", error=_("New password has to be atleast 8 characters long, with no whitespaces"))

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute(
            """
                SELECT password, userid FROM Users WHERE Email = ?
            """, email_for_password_reset
        )
        row = cursor.fetchone()
        stored_hash = row[0]
        userid = row[1]

        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')    

        if bcrypt.checkpw(new_password.encode('utf-8'), stored_hash):
            return render_template("reset_password.html", error=_("New Password musn't be previously used password"))

        bytes = new_password.encode('utf-8')
        salt = bcrypt.gensalt()
        hash = bcrypt.hashpw(bytes, salt)
        hash_str = hash.decode('utf-8')

        cursor.execute("""
            UPDATE Users
            SET password = ?
            WHERE email = ?
        """, (hash_str, email_for_password_reset))
        
        conn.commit()
        cursor.close()
        conn.close()

        create_notification(userid, _("Password changed successfully"), link=url_for('profile'), icon='fa-unlock')
        log_user_action(action_type='resetUserPassword', status='SUCCESS', resource_id='resetPassword')
        return render_template("reset_password.html", message=_("Password changed"))
    except Exception as e:
        log_user_action(action_type='resetUserPassword', status='FAILURE', resource_id='resetPassword', details={"serverError": str(e)}, IsInternalError=1)
        return 
    
@app.route('/reset_password/<token>')
def reset_password(token):
    try:
        session['email_for_password_reset'] = s.loads(token, salt='password-reset-salt', max_age=900)
        return render_template('reset_password.html')
    except Exception:
        return redirect(url_for('index'))
    
def send_reset_email(email):
    def get_link():
        token = s.dumps(email, salt='password-reset-salt')
        link = url_for('reset_password', token=token, _external=True)
        return link

    def get_access_token():
        uri = f'https://login.microsoftonline.com/{GRAPH_TENANT_ID}/oauth2/v2.0/token'
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        body = {
            "client_id": GRAPH_CLIENT_ID,
            "username": GRAPH_USERNAME,
            "password": GRAPH_PASSWORD,
            "grant_type": "password",
            "scope": "Mail.Send",
            "client_secret": GRAPH_CLIENT_SECRET
        }
        try:
            response  = requests.post(uri, headers=headers, data=body)
            return response.json()['access_token']
        except Exception as e:
            print(e)

    uri = 'https://graph.microsoft.com/v1.0/me/sendMail'
    access_token = get_access_token()
    headers = {
        'Authorization': f'Bearer {access_token}',
    }
    link = get_link()
    try:
        body = {
            "message": {
                "subject": _("nexora Password Reset Request"),
                "body": {
                    "contentType": "HTML",
                    "content": f"""
                            <!DOCTYPE html>
                            <html lang="en">
                            <head>
                                <meta charset="UTF-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                <meta http-equiv="X-UA-Compatible" content="ie=edge">
                                <title>Password Reset Request</title>
                                <style>
                                    body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
                                    table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
                                    img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
                                    table {{ border-collapse: collapse !important; }}
                                    body {{ height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; font-family: Arial, sans-serif; }}

                                    @media screen and (max-width: 600px) {{
                                        .email-container {{
                                            width: 100% !important;
                                            max-width: 100% !important;
                                            margin: auto !important;
                                        }}
                                    }}
                                </style>
                            </head>
                            <body style="margin: 0; padding: 0; background-color: #f4f4f4;">
                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                    <tr>
                                        <td align="center" style="background-color: #f4f4f4;">
                                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;" class="email-container">
                                                <tr>
                                                    <td align="center" style="padding: 10px 0 10px 0; background-color: #ffffff;">
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="background-color: #ffffff;">
                                                        <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                                            <tr>
                                                                <td style="padding: 20px 30px 40px 30px; text-align: left;">
                                                                    <h1 style="margin: 0; font-family: Arial, sans-serif; font-size: 24px; font-weight: bold; color: #333333;">
                                                                        {_("Password Reset Request")}
                                                                    </h1>
                                                                    <p style="margin: 20px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        {_("Hello,")}
                                                                    </p>
                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        {_("We received a request to reset the password for your account. You can reset your password by clicking the button below.")}
                                                                    </p>
                                                                    
                                                                    <table border="0" cellspacing="0" cellpadding="0" width="100%" style="margin-top: 30px; margin-bottom: 30px;">
                                                                        <tr>
                                                                            <td align="center">
                                                                                <table border="0" cellspacing="0" cellpadding="0">
                                                                                    <tr>
                                                                                        <td align="center" style="border-radius: 5px; background-color: #3b82f6;">
                                                                                            <a href="{link}" target="_blank" style="font-size: 16px; font-family: Arial, sans-serif; font-weight: bold; color: #ffffff; text-decoration: none; border-radius: 5px; padding: 15px 25px; border: 1px solid #4338ca; display: inline-block;">
                                                                                                {_("Reset Your Password")}
                                                                                            </a>
                                                                                        </td>
                                                                                    </tr>
                                                                                </table>
                                                                            </td>
                                                                        </tr>
                                                                    </table>

                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        {_("If you did not request a password reset, please ignore this email. This link is valid for 15 minutes.")}
                                                                    </p>
                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        {_("Thanks,<br>The Sydoc Team")}
                                                                    </p>
                                                                </td>
                                                            </tr>
                                                        </table>
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 20px 30px; background-color: #eeeeee; text-align: center;">
                                                        <p style="margin: 0; font-family: Arial, sans-serif; font-size: 12px; color: #888888;">
                                                            &copy; 2025 Sydoc AG. All rights reserved.<br>
                                                            Mühlegasse 18, 6340 Baar
                                                        </p>
                                                    </td>
                                                </tr>
                                            </table>
                                        </td>
                                    </tr>
                                </table>
                            </body>
                            </html>
                    """
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": email
                        }
                    }
                ]
            },
            "saveToSentItems": True 
        }

        response = requests.post(uri, headers=headers, json=body)
        response.raise_for_status()  
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response body: {response.text}") 
        return False
    except Exception as e:
        print(f"An other error occurred: {e}")
        return False

@limiter.limit("5 per hour") 
@app.route('/request-password-reset', methods=['GET', 'POST'])
def request_password_reset():
    request_email = request.form['email']
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER_PRD},1433;'
        f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
        f'UID={DB_UID};'
        f'PWD={DB_PWD};'
        f'TrustServerCertificate=yes;'
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users WHERE Email = ?", (request_email))
    rows = cursor.fetchone()

    if rows:
        sendreset = send_reset_email(request_email)
        if sendreset:
            return render_template("forgot_password.html", message=_("A password reset link has been sent to your email"))
        else:
            return render_template('forgot_password.html', error=_("Unexpected error occurred"))
    return render_template('forgot_password.html', error=_("Invalid Email Address"))
# ---------------------------- forgot password end --------------------------- #

# ------------------------------ process filter ------------------------------ #
def get_process_filter_and_params(process_name):
    if process_name == '02_Posteingang':
        return "?", ["02_Posteingang"]
    elif process_name == '02_Invoice':
        return "?", ["02_Invoice"]
    else:
        return "?, ?", ["02_Posteingang", "02_Invoice"]
# ---------------------------- process filter end ---------------------------- #

# --------------------------------- dashboard -------------------------------- #
def get_absolute_dashboard_stats(processName="both"):
    stats = {}
    conn = None
    try:
        placeholders, params = get_process_filter_and_params(processName)
        all_params = params + ['Privera'] + params + ['Privera']
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_RUNTIME};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            WITH AllStatuses
            AS (SELECT 0 AS StatusCode,
                    'Ready' AS StatusName
                UNION ALL
                SELECT 1,
                    'In Progress'
                UNION ALL
                SELECT 5,
                    'Done'
            ),
                ActualCounts
            AS (SELECT COUNT(w.id) as WorkitemCount,
                    w.[Status]
                FROM t_WorkItems w
                    LEFT JOIN t_ActivityInstances a
                        on a.id = w.ActivityInstanceID
                    LEFT JOIN t_Processes p
                        on p.id = a.ProcessID
                WHERE p.Name IN ({placeholders})
                    AND p.ClientName = ?
                GROUP BY w.[Status]
            )
            SELECT ISNULL(ac.WorkitemCount, 0) AS WorkitemCount,
                s.StatusName AS Status
            FROM AllStatuses s
                LEFT JOIN ActualCounts ac
                    ON s.StatusCode = ac.Status
            UNION ALL
            SELECT COUNT(*),
                'Backlog'
            FROM t_WorkItems w
                LEFT JOIN t_ActivityInstances a
                    on a.id = w.ActivityInstanceID
                LEFT JOIN t_Processes p
                    on p.id = a.ProcessID
            WHERE p.Name IN ({placeholders})
                AND p.ClientName = ?
                AND a.ActivityInstanceName = 'C+A';
            """, all_params
        )
        rows = cursor.fetchall()
        stats['ReadyTotal'] = rows[0][0]
        stats['InProgressTotal'] = rows[1][0]
        stats['DoneTotal'] = rows[2][0]
        stats['BacklogTotal'] = rows[3][0]

    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()
    return stats

def get_dashbord_preview_documents_stats(processName='both'):
    stats = {}
    conn = None
    try:
        placeholders, params = get_process_filter_and_params(processName)
        all_params = params + ['Privera']
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_RUNTIME};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(f"""
            WITH CTE AS (
            SELECT tdi.WorkItemID, DATEADD(HOUR, 2, twi.ModifiedAt) ModifiedAt, 
            CASE 
                WHEN twi.Status = 0 THEN 'Ready'
                WHEN twi.Status = 5 THEN 'Done'
                ELSE 'In Progress'
            END AS Status,
            CASE
                    WHEN tai.ActivityInstanceName like '%C+A%' THEN
                        'InValidation'
                    WHEN tai.ActivityInstanceName like '%Export%'
                        OR tai.ActivityInstanceName like '%Exp%' THEN
                        'InExport'
                    WHEN tai.ActivityInstanceName like '%Import%'
                        OR tai.ActivityInstanceName like '%Imp%' THEN
                        'InImport'
                    WHEN tai.ActivityInstanceName like '%Extract%' THEN
                        'InExtraction'
                    WHEN tai.ActivityInstanceName like '%OCR%' THEN
                        'InOCR'
                    WHEN tai.ActivityInstanceName like '%Statistik%' THEN
                        'InDBSaving'
                    WHEN tai.ActivityInstanceName like '%Collect%' THEN
                        'InDBSaving'
                    ELSE
                        'Processing'
                END AS Activity
            FROM t_WorkItems twi 
            LEFT JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID 
            LEFT JOIN t_Processes tp ON tp.ID = tai.ProcessID
            LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = twi.ID
            WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ? AND
            tdi.Name = 'PLATFORM_DocumentType' AND tdi.StringValue LIKE '%Document'
            AND twi.Status <> 2 
        )
        SELECT DISTINCT TOP 10 tdi.StringValue Barcode
        ,Activity FROM CTE
        LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = CTE.WorkItemID 
        WHERE tdi.Name LIKE '%Barcode' and tdi.StringValue is not NULL
        AND CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
            """, (all_params)
        )
        rows = cursor.fetchall()
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()

    return jsonify([
            {
                "Barcode": row[0],
                "Activity": row[1]
            }
            for row in rows
        ])

@app.route("/dashboard")
def dashboard():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        
        logged_in_user = session.get('username', 'Unknown')
        scope = session.get('scope', 'Unknown')
        userid = session.get('userid', 'Unknown')

        process_name = request.args.get('processFilterDashboard', 'both')
        session['process_name_dashboard'] = process_name
        absolute_stats = get_absolute_dashboard_stats(process_name)

        log_user_action(action_type='visitDashboard', status='SUCCESS', resource_id='dashboard')
        return render_template("dashboard.html", 
        logged_in_user=logged_in_user,
        scope=scope,
        userid=userid,
        ReadyTotal=absolute_stats['ReadyTotal'],
        InProgressTotal=absolute_stats['InProgressTotal'],
        DoneTotal=absolute_stats['DoneTotal'],
        BacklogTotal=absolute_stats['BacklogTotal'], process_name=process_name
        )
    except Exception as e:
        log_user_action(action_type='visitDashboard', status='FAILURE', resource_id='dashboard', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

@app.route("/api/dashboard_stats_absolute")
def dashboard_stats_absolute():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    process_name = session['process_name_dashboard']
    stats = get_absolute_dashboard_stats(process_name)
    return jsonify(stats) 

@app.route("/api/dashboard_stats_document_preview")
def dashboard_stats_document_preview():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    process_name = session['process_name_dashboard']
    stats = get_dashbord_preview_documents_stats(process_name)
    return stats

@app.route('/api/recent_activity')
def recent_activity():
    if 'username' not in session:
        return jsonify({"error": _("Not logged in")}), 401
    
    placeholders, params = get_process_filter_and_params(session['process_name_dashboard'])
    all_params = params + ['Privera']

    try:
        conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER_PRD},1433;'
                f'DATABASE={DB_SERVER_DB_RUNTIME};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};'
                f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        query = f"""
            WITH CTE AS (
            SELECT tdi.WorkItemID, DATEADD(HOUR, 2, twi.ModifiedAt) ModifiedAt, 
            CASE 
                WHEN twi.Status = 0 THEN 'Ready'
                WHEN twi.Status = 5 THEN 'Done'
                ELSE 'In Progress'
            END AS Status
            FROM t_WorkItems twi 
            LEFT JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID 
            LEFT JOIN t_Processes tp ON tp.ID = tai.ProcessID
            LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = twi.ID
            WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ? AND
            tdi.Name = 'PLATFORM_DocumentType' AND tdi.StringValue LIKE '%Document'
            AND twi.Status <> 2 
        )
        SELECT DISTINCT TOP 4 tdi.StringValue Barcode, CTE.Status, CTE.ModifiedAt FROM CTE
        LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = CTE.WorkItemID 
        WHERE tdi.Name LIKE '%Barcode' and tdi.StringValue is not NULL
        AND CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
        """
        cursor.execute(query, all_params)
        activities = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([
            {
                "state": row[1],
                "datetime": row[2].strftime('%Y-%m-%d %H:%M:%S'),  
                "Barcode": row[0]
            }
            for row in activities
        ])
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500
# ------------------------------- dashboard end ------------------------------ #

# ----------------------------- workitem overview ---------------------------- #
@app.route("/api/workitems")
def api_workitems():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))

        logged_in_user = session.get('username')
        userid = session.get('userid')
        scope = session.get('scope')

        page = request.args.get('page', 1, type=int)
        search_term = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        tag_filter = request.args.get('tag', '').strip() 
        start_date = request.args.get('startDate', '')
        end_date = request.args.get('endDate', '')
        start_date = datetime.fromisoformat(start_date) if start_date else None
        end_date = datetime.fromisoformat(end_date) if end_date else None
        priority = request.args.get('priority', '')
        assigned_user = request.args.get('assignedUser', '')
        per_page = 40
        offset = (page - 1) * per_page

        process_name = request.args.get('processFilterWorkitemOverview', 'both')
        session['process_name_workitemOverview'] = process_name
        placeholders, params = get_process_filter_and_params(process_name)
        params.append('Privera')

        where_clauses = [
            f"tp.Name IN ({placeholders})",
            "tp.ClientName = ?",
            "twi.Status <> 2",
            "tdi_barcode.Name LIKE '%Barcode'", 
            "tdi_barcode.StringValue IS NOT NULL"
        ]
        status_map = {'Ready': 0, 'In Progress': 1, 'Done': 5}
        if status and status in status_map:
            where_clauses.append("twi.Status = ?")
            params.append(status_map[status])
        if tag_filter:
            where_clauses.append(f"""
                EXISTS (
                    SELECT 1
                    FROM [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Tags wt
                    JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Tags t ON wt.TagID = t.TagID
                    WHERE wt.Barcode = tdi_barcode.StringValue AND t.TagName like ?
                )
            """)
            params.append('%'+tag_filter+'%')

        if search_term:
            where_clauses.append("tdi_barcode.StringValue LIKE ?")
            params.append(f"%{search_term}%")

        if start_date:
            where_clauses.append("twi.ModifiedAt >= ?")
            params.append(start_date)

        if end_date:
            where_clauses.append("twi.ModifiedAt < ?")
            params.append(end_date)
        if priority:
            where_clauses.append("wim.Priority = ?")
            params.append(priority)
        if assigned_user:
            if assigned_user == 'None' or assigned_user == 'Unassigned':
                where_clauses.append("(wim.AssignedUserID IS NULL)")
            else:
                where_clauses.append("wim.AssignedUserID = ?")
                params.append(assigned_user)

        where_sql = " AND ".join(where_clauses)

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_RUNTIME};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        workitems_list = []
        total_items = 0
        conn = None
        # Get all workitems
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute(f"""
            SELECT COUNT(DISTINCT tdi_barcode.StringValue)
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                INNER JOIN t_DocumentIndexes tdi_barcode ON twi.ID = tdi_barcode.WorkItemID
                LEFT JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Metadata wim ON tdi_barcode.StringValue = wim.Barcode
                WHERE {where_sql}
            """, params)

            total_items = cursor.fetchone()[0] or 0
            data_query = f"""
                    WITH WorkitemCTE AS (
                        SELECT
                            tdi_barcode.StringValue AS Barcode,
                            twi.ModifiedAt,
                            twi.ID AS WorkItemID,
                            CASE
                                WHEN twi.Status = 0 THEN 'Ready'
                                WHEN twi.Status = 5 THEN 'Done'
                                ELSE 'In Progress'
                            END AS Status,
                            wim.Priority,
                            (
                                SELECT 
                                    t.TagID AS id,
                                    t.TagName AS name,
                                    t.TagColor AS color
                                FROM [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Tags wt
                                JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Tags t ON wt.TagID = t.TagID
                                WHERE wt.Barcode = tdi_barcode.StringValue
                                FOR JSON PATH
                            ) AS TagsJSON,
                            ROW_NUMBER() OVER(PARTITION BY tdi_barcode.StringValue ORDER BY twi.ModifiedAt DESC) as rn
                        FROM t_WorkItems twi
                        INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                        INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                        INNER JOIN t_DocumentIndexes tdi_barcode ON twi.ID = tdi_barcode.WorkItemID
                        LEFT JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Metadata wim ON tdi_barcode.StringValue = wim.Barcode
                        WHERE {where_sql}
                    )
                    SELECT Barcode, ModifiedAt, WorkItemID, Status, Priority, TagsJSON
                    FROM WorkitemCTE
                    WHERE rn = 1
                    ORDER BY ModifiedAt DESC
                    OFFSET ? ROWS
                    FETCH NEXT ? ROWS ONLY
"""
            data_params = params + [offset, per_page] 
            cursor.execute(data_query, data_params)

            for row in cursor.fetchall():
                workitems_list.append({
                    'barcode': row.Barcode,
                    'modifiedat': row.ModifiedAt,
                    'workitemid': row.WorkItemID,
                    'status': row.Status,
                    'priority': row.Priority or 0,
                    'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
                })
        except Exception as e:
            app.logger.error(f"Database error in workitems overview: {e}")
            workitems_list = []
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
        total_pages = math.ceil(total_items / per_page)

        log_user_action('visitWorkitemOverview', status='SUCCESS', resource_id='workitemOverview')

        return jsonify({
        'workitems': workitems_list,
        'pagination': {
            'currentPage': page,
            'totalPages': total_pages,
            'totalItems': total_items,
            'perPage': per_page
            }
        })
    except Exception as e:
        log_user_action('visitWorkitemOverview', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

@app.route("/workitems")
def workitems_overview():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))

        logged_in_user = session.get('username')
        userid = session.get('userid')
        scope = session.get('scope')
        access = session.get('access')

        page = request.args.get('page', 1, type=int)
        search_term = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        tag_filter = request.args.get('tag', '').strip()         
        start_date = request.args.get('startDate', '')
        end_date = request.args.get('endDate', '')
        start_date = datetime.fromisoformat(start_date) if start_date else None
        end_date = datetime.fromisoformat(end_date) if end_date else None
        priority = request.args.get('priority', '')
        assigned_user = request.args.get('assignedUser', '')
        per_page = 40
        offset = (page - 1) * per_page

        process_name = request.args.get('processFilterWorkitemOverview', 'both')
        session['process_name_workitemOverview'] = process_name
        placeholders, params = get_process_filter_and_params(process_name)
        params.append('Privera')

        where_clauses = [
            f"tp.Name IN ({placeholders})",
            "tp.ClientName = ?",
            "twi.Status <> 2",
            "tdi_barcode.Name LIKE '%Barcode'", 
            "tdi_barcode.StringValue IS NOT NULL"
        ]
        status_map = {'Ready': 0, 'In Progress': 1, 'Done': 5}
        if status and status in status_map:
            where_clauses.append("twi.Status = ?")
            params.append(status_map[status])

        if search_term:
            where_clauses.append("tdi_barcode.StringValue LIKE ?")
            params.append(f"%{search_term}%")
        if tag_filter:
            where_clauses.append(f"""
                EXISTS (
                    SELECT 1
                    FROM [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Tags wt
                    JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Tags t ON wt.TagID = t.TagID
                    WHERE wt.Barcode = tdi_barcode.StringValue AND t.TagName like ?
                )
            """)
            params.append('%'+tag_filter+'%')
        if start_date:
            where_clauses.append("twi.ModifiedAt >= ?")
            params.append(start_date)

        if end_date:
            where_clauses.append("twi.ModifiedAt < ?")
            params.append(end_date)

        if priority:
            where_clauses.append("wim.Priority = ?")
            params.append(priority)
        if assigned_user:
            if assigned_user == 'None' or assigned_user == 'Unassigned':
                where_clauses.append("(wim.AssignedUserID IS NULL)")
            else:
                where_clauses.append("wim.AssignedUserID = ?")
                params.append(assigned_user)
        where_sql = " AND ".join(where_clauses)

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_RUNTIME};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        workitems_list = []
        total_items = 0
        conn = None
        # Get all workitems
        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            cursor.execute(f"""
            SELECT COUNT(DISTINCT tdi_barcode.StringValue)
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                INNER JOIN t_DocumentIndexes tdi_barcode ON twi.ID = tdi_barcode.WorkItemID
                LEFT JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Metadata wim ON tdi_barcode.StringValue = wim.Barcode
                WHERE {where_sql}
            """, params)
            total_items = cursor.fetchone()[0] or 0

            data_query = f"""
                    WITH WorkitemCTE AS (
                        SELECT
                            tdi_barcode.StringValue AS Barcode,
                            twi.ModifiedAt,
                            twi.ID AS WorkItemID,
                            CASE
                                WHEN twi.Status = 0 THEN 'Ready'
                                WHEN twi.Status = 5 THEN 'Done'
                                ELSE 'In Progress'
                            END AS Status,
                            wim.Priority,
                            (
                                SELECT 
                                    t.TagID AS id,
                                    t.TagName AS name,
                                    t.TagColor AS color
                                FROM [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Tags wt
                                JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Tags t ON wt.TagID = t.TagID
                                WHERE wt.Barcode = tdi_barcode.StringValue
                                FOR JSON PATH
                            ) AS TagsJSON,
                            ROW_NUMBER() OVER(PARTITION BY tdi_barcode.StringValue ORDER BY twi.ModifiedAt DESC) as rn
                        FROM t_WorkItems twi
                        INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                        INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                        INNER JOIN t_DocumentIndexes tdi_barcode ON twi.ID = tdi_barcode.WorkItemID
                        LEFT JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Metadata wim ON tdi_barcode.StringValue = wim.Barcode
                        WHERE {where_sql}
                    )
                    SELECT Barcode, ModifiedAt, WorkItemID, Status, Priority, TagsJSON
                    FROM WorkitemCTE
                    WHERE rn = 1
                    ORDER BY ModifiedAt DESC
                    OFFSET ? ROWS
                    FETCH NEXT ? ROWS ONLY
            """
            data_params = params + [offset, per_page]
            cursor.execute(data_query, data_params)

            for row in cursor.fetchall():
                workitems_list.append({
                    'barcode': row.Barcode,
                    'modifiedat': row.ModifiedAt,
                    'workitemid': row.WorkItemID,
                    'status': row.Status,
                    'priority': row.Priority or 0,
                    'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
                })
                
        except Exception as e:
            app.logger.error(f"Database error in workitems overview: {e}")
            workitems_list = []
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
        total_pages = math.ceil(total_items / per_page)

        log_user_action('visitWorkitemOverview', status='SUCCESS', resource_id='workitemOverview')
        portal_users = get_all_portal_users(access)

        return render_template("workitems_overview.html", 
            logged_in_user=logged_in_user,
            userid=userid,
            scope=scope,
            process_name=process_name,
            workitems=workitems_list,
            current_page=page,
            total_pages=total_pages,
            total_items=total_items,
            search=search_term,
            status=status,
            startDate=start_date,
            endDate=end_date,
            priority=priority,
            assignedUser=assigned_user,
            portal_users=portal_users
        )
    except Exception as e:
        log_user_action('visitWorkitemOverview', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

@app.route('/import_workitems', methods=['POST'])
def import_workitems():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if 'importFile' not in request.files:
        flash(_("No file part in the request."), 'error')
        return redirect(url_for('workitems_overview'))

    file = request.files['importFile']

    if file.filename == '':
        flash(_("No file selected for uploading."), 'error')
        return redirect(url_for('workitems_overview'))

    if file:
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(app.root_path, 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        
        try:
            file.save(file_path)
            log_user_action('importWorkitems', status='SUCCESS', resource_id='workitemOverview', details={'filename': filename})
            flash(_("File '{}' successfully imported.").format(filename), 'success')
        except Exception as e:
            app.logger.error(f"Error saving imported file: {e}")
            log_user_action('importWorkitems', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
            flash(_("An error occurred while saving the file."), 'error')

    return redirect(url_for('workitems_overview'))

@app.route('/api/workitem/<barcode>')
def get_single_workitem(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_RUNTIME};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        query = f"""
            WITH WorkitemCTE AS (
                SELECT
                    tdi_barcode.StringValue AS Barcode,
                    twi.ID AS WorkItemID,
                    (
                        SELECT 
                            t.TagID AS id,
                            t.TagName AS name,
                            t.TagColor AS color
                        FROM [{DB_SERVER_DB_WEBPORTAL}].dbo.Workitem_Tags wt
                        JOIN [{DB_SERVER_DB_WEBPORTAL}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.Barcode = tdi_barcode.StringValue
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY tdi_barcode.StringValue ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                INNER JOIN t_DocumentIndexes tdi_barcode ON twi.ID = tdi_barcode.WorkItemID
                WHERE tdi_barcode.StringValue = ?
            )
            SELECT Barcode, WorkItemID, TagsJSON
            FROM WorkitemCTE
            WHERE rn = 1
        """
        cursor.execute(query, barcode)
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Workitem not found"}), 404

        workitem_data = {
            'barcode': row.Barcode,
            'workitemid': row.WorkItemID,
            'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
        }
        return jsonify(workitem_data)
    except Exception as e:
        app.logger.error(f"Failed to fetch single workitem {barcode}: {e}")
        return jsonify({"error": "Could not fetch workitem data"}), 500
    finally:
        if conn:
            conn.close()

def get_access_token():
    token = cache.get('octo_access_token')
    if token:
        return token

    url = 'https://prd-dps.sydoc.ch/auth/connect/token'
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    body = {
        "grant_type": OCTO_GRANT_TYPE,
        "client_id": OCTO_CLIENT_ID,
        "client_secret": OCTO_CLIENT_SECRET
    }

    try:
        response = requests.post(url=url, headers=headers, data=body)
        response.raise_for_status() 
        data = response.json()
        
        timeout = data.get('expires_in', 3000) - 60 
        token = data['access_token']
        cache.set('octo_access_token', token, timeout=timeout)
        return token
    except requests.exceptions.RequestException as e:
        print(f"Error fetching access token: {e}")
        return None

def get_workitemdata_param(workitem_id):
    url = f'https://prd-dps.sydoc.ch/api/processservice/api/v2.1/processService/WorkItems/{workitem_id}/load'
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url=url, headers=headers)
    str_content = json.dumps(response.json())
    base64_bytes = base64.b64encode(str_content.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')

    return base64_string, response.json()['DocumentID']

def get_extensions_urls_fields(workitemdata, document_id):
    url = f'https://prd-dps.sydoc.ch/api/documentservice/api/v2.1/documentService/thin/Document/{document_id}?WithExtensions=false&WithDocumentStructure=true&WithTables=false&WithDocumentAudits=true&LoadMediaStreams=true'
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "workitemdata": workitemdata
    }
    response = requests.get(url=url, headers=headers)
    urls = []
    extension = []
    fields = {}
    isP = False

    for customvalues in response.json()['CustomValues']:
        if customvalues['Key'] == 'FilePath' and 'posteingang' in customvalues['Value']:
            isP = True
            break
    
    if response.json()['DocumentType'] == 'Batch' and response.json()['ChildDocuments'] != None:
        for element in response.json()['ChildDocuments']:
            for media in element['Media']:
                if str(media['Extension']).lower() in ('.jpg', '.jpeg', '.png', '.tif'):
                    urls.append(media['Url'])
                    extension.append(media['Extension'])
            for field in element['IndexFields']:
                if field['Name'] == 'exp_dokDatum':
                    fields['DocDate'] = field["FieldValue"]['Text']
                elif field['Name'] == 'exp_dokTyp':
                    fields['DocType'] = field["FieldValue"]['Text']

                elif field['Name'] == 'exp_eigNr':
                    fields['OwnerNr'] = field["FieldValue"]['Text']
                elif field['Name'] == 'eigentuemerName':
                    fields['OwnerName'] = field["FieldValue"]['Text']

                elif field['Name'] == 'exp_liegNr':
                    fields['PropertyNr'] = field["FieldValue"]['Text']
                elif field['Name'] == 'liegenschaftName':
                    fields['PropertyName'] = field["FieldValue"]['Text']

                elif field['Name'] == 'exp_mietNr':
                    fields['TenantNr'] = field["FieldValue"]['Text']
                elif field['Name'] == 'mieterName':
                    fields['TenantName'] = field["FieldValue"]['Text']
                
                elif field['Name'] == 'exp_sendNr':
                    fields['BroadcastNr'] = field["FieldValue"]['Text']
                
                elif field['Name'] == 'exp_niederlassung':
                    fields['Branch'] = field["FieldValue"]['Text']
    
    elif isP:
        for element in response.json()['Media']:
            if str(element['Extension']).lower() in ('.jpg', '.jpeg', '.png', '.tif'):
                urls.append(element['Url'])
                extension.append(element['Extension'])
        for field in response.json()['IndexFields']:
            if field['Name'] == 'exp_dokDatum':
                fields['DocDate'] = field["FieldValue"]['Text']
            elif field['Name'] == 'exp_dokTyp':
                fields['DocType'] = field["FieldValue"]['Text']

            elif field['Name'] == 'exp_eigNr':
                fields['OwnerNr'] = field["FieldValue"]['Text']
            elif field['Name'] == 'eigentuemerName':
                fields['OwnerName'] = field["FieldValue"]['Text']

            elif field['Name'] == 'exp_liegNr':
                fields['PropertyNr'] = field["FieldValue"]['Text']
            elif field['Name'] == 'liegenschaftName':
                fields['PropertyName'] = field["FieldValue"]['Text']

            elif field['Name'] == 'exp_mietNr':
                fields['TenantNr'] = field["FieldValue"]['Text']
            elif field['Name'] == 'mieterName':
                fields['TenantName'] = field["FieldValue"]['Text']
            
            elif field['Name'] == 'exp_sendNr':
                fields['BroadcastNr'] = field["FieldValue"]['Text']
            
            elif field['Name'] == 'exp_niederlassung':
                fields['Branch'] = field["FieldValue"]['Text']
    
    else:
        for element in response.json()['Media']:
            if str(element['Extension']).lower() in ('.jpg', '.jpeg', '.png', '.tif'):
                urls.append(element['Url'])
                extension.append(element['Extension'])
        for element in response.json()['IndexFields']:
            if element['Name'] == 'CrdName':
                fields['CrdName'] = element["FieldValue"]['Text']
            elif element['Name'] == 'DocNo':
                fields['DocNo'] = element["FieldValue"]['Text']
            elif element['Name'] == 'CrdNo':
                fields['CrdNo'] = element["FieldValue"]['Text']
            elif element['Name'] == 'GrossAmount':
                fields['GrossAmount'] = element["FieldValue"]['Text']
            elif element['Name'] == 'NetAmount':
                fields['NetAmount'] = element["FieldValue"]['Text']
            elif element['Name'] == 'VatAmount':
                fields['VatAmount'] = element["FieldValue"]['Text']
            elif element['Name'] == 'DocType':
                fields['DocType'] = element["FieldValue"]['Text']
    return extension, urls, fields

def get_media(url):
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url=url, headers=headers)
    return response.content

cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 300}) 

@app.route('/api/get_media_info/<int:workitem_id>')
def api_get_media_info(workitem_id):
    try:
        cached_info = cache.get(f"media_info_{workitem_id}")
        if cached_info:
            return jsonify(cached_info)

        returndata = get_workitemdata_param(workitem_id)
        if not returndata:
            return jsonify({"error": _("Workitem not found")}), 404

        workitemdata, document_id = returndata
        extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id)
        
        media_count = len(urls) if urls else 0
        
        if media_count > 0:
            cache.set(f"media_data_{workitem_id}", {'extensions': extensions, 'urls': urls})

        response_data = {
            "workitem_id": workitem_id,
            "media_count": media_count,
            "fields": fields
        }
        
        cache.set(f"media_info_{workitem_id}", response_data)
        return jsonify(response_data)
    except Exception as e:
        print(f"An error occurred in get_media_info: {e}")
        print(workitem_id)
        return jsonify({"error": _("Internal Server Error")}), 500
    
@app.route('/api/get_media_raw/<int:workitem_id>/<int:media_index>')
def api_get_media_raw(workitem_id, media_index):
    try:
        media_data = cache.get(f"media_data_{workitem_id}")
        if not media_data:
            returndata = get_workitemdata_param(workitem_id)
            if not returndata:
                return Response(_("Workitem not found"), status=404)

            workitemdata, document_id = returndata
            extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id)
            media_data = {'extensions': extensions, 'urls': urls}
            cache.set(f"media_data_{workitem_id}", media_data)
        
        extensions = media_data.get('extensions', [])
        urls = media_data.get('urls', [])

        if media_index >= len(urls):
            return Response(_("Media index out of bounds"), status=404)

        target_url = urls[media_index]
        target_extension = extensions[media_index].lower()
        
        raw_media_bytes = get_media(target_url) 

        if target_extension == '.jpg':
            mimetype = 'image/jpeg'
        elif target_extension == '.png':
            mimetype = 'image/png'
        elif target_extension == '.tif':
            try:
                image_stream = io.BytesIO(raw_media_bytes)
                with Image.open(image_stream) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=85) 
                    buffer.seek(0)
                    
                    return send_file(
                        buffer,
                        mimetype='image/jpeg',
                        as_attachment=False 
                    )
            except Exception as e:
                print(f"An error occurred during TIFF conversion: {e}")
                return _("Failed to process TIFF image"), 500
            
        response = make_response(raw_media_bytes)
        response.headers.set('Content-Type', mimetype)
        
        response.headers.set(
            'Cache-Control', 'public, max-age=3600'
        )
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return Response(_("Internal Server Error"), status=500)

@cache.memoize() 
def get_activity_type_name(activity_instance_id: str) -> str:
    activity_instances_url = f'https://prd-dps.sydoc.ch/api/configurationservice/api/v2.1/configservice/ActivityInstances/{activity_instance_id}'
    access_token = get_access_token() 
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        response = requests.get(url=activity_instances_url, headers=headers)
        response.raise_for_status() 
        activity_instance_config = response.json()
        return activity_instance_config.get('ActivityTypeName', 'Unknown Activity')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching activity instance {activity_instance_id}: {e}")
        return _("Error fetching activity instance")

@app.route('/api/get_audithistory/<int:workitem_id>')
def get_audithistory(workitem_id):
    try:
        audit_url = f'https://prd-dps.sydoc.ch/api/processservice/api/v2.1/processService/WorkItemAudits?WorkItemID={workitem_id}&VerifyAuditSignatures=true&ExportSignatureVerificationCertificates=true'
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url=audit_url, headers=headers)
        response.raise_for_status()
        audits = response.json()

        unique_activities = {}
        for audit in audits.get('Audits', []):
            activity_id = audit.get('ActivityInstanceID')
            if activity_id and activity_id not in unique_activities:
                unique_activities[activity_id] = datetime.fromisoformat(audit['TimeStamp']).strftime("%Y-%m-%d %H:%M:%S")

        complete_array = []
        total_steps = len(unique_activities)
        
        for i, (activity_id, time_stamp) in enumerate(unique_activities.items()):
            activity_name = get_activity_type_name(activity_id) 
            
            step_info = {
                "Activity": activity_name,
                "DateTime": time_stamp,
                "Step": total_steps - i 
            }
            complete_array.append(step_info)
        
        return jsonify(complete_array)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"{_("Failed to fetch audit history")}: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"{_("An unexpected error occurred")}: {e}"}), 500

# ------------------------ workitem collaboration apis ----------------------- #
@app.route('/api/users')
def get_users_for_mentions():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT userID, username, fullname FROM Users WHERE access = ?", (session.get('access'),))
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(users)
    except Exception as e:
        app.logger.error(f"Failed to fetch users for mentions: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/interactions')
def get_workitem_interactions(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("""SELECT Priority, AssignedUserID FROM Workitem_Metadata
                        WHERE Barcode = ?"""
                       , (barcode,))
        row = cursor.fetchone()
        if not row:
            return jsonify({
                'priority': 0,
                'assigneduserid': 'None',
                'comments': [],
                'tags': [], 
                'message': _("No data found for this workitem.")
            }), 200
        priority = row[0] if row[0] != None else 0
        assigneduserid = row[1] if row[1] != None else 'None'
        current_user_access = session.get('access')

        sql_query = """
            SELECT c.CommentText, c.Timestamp, u.username, u.userID
            FROM Workitem_Comments c
            JOIN Users u ON c.UserID = u.userID
        """
        params = [barcode]

        cursor.execute("""
            SELECT t.TagID, t.TagName, t.TagColor
            FROM Workitem_Tags wt
            JOIN Tags t ON wt.TagID = t.TagID
            WHERE wt.Barcode = ?
        """, (barcode,))
        tags_data = cursor.fetchall()
        tags = [{'id': row.TagID, 'name': row.TagName, 'color': row.TagColor} for row in tags_data]

        if current_user_access == 'Unlimited':
            sql_query += " WHERE c.Barcode = ?"
        else:
            sql_query += " WHERE c.Barcode = ? AND u.access = ?"
            params.append(current_user_access)
        
        sql_query += " ORDER BY c.Timestamp ASC"
        cursor.execute(sql_query, params)
        comments_data = cursor.fetchall()
        comments = []
        for row in comments_data:
            comments.append({
                'CommentText': row.CommentText,
                'Timestamp': row.Timestamp.isoformat(),
                'username': row.username,
                'userID': row.userID
            })
        return jsonify({
            'priority': priority,
            'assigneduserid': assigneduserid,
            'comments': comments,
            'tags': tags 
        })
    except Exception as e:
        app.logger.error(f"Failed to fetch interactions for barcode {barcode}: {e}")
        return jsonify({"error": _("Could not fetch interactions")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/comment', methods=['POST'])
def add_workitem_comment(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    data = request.get_json()
    comment_text = data.get('commentText')
    if not comment_text:
        return jsonify({'success': False, 'message': _("Comment cannot be empty.")}), 400

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO Workitem_Comments (Barcode, UserID, CommentText)
            VALUES (?, ?, ?)
        """, (barcode, session['userid'], comment_text))
        
        cursor.execute("SELECT SCOPE_IDENTITY()")
        comment_id = cursor.fetchone()[0]
        
        mentions = re.findall(r'@(\w+)', comment_text)
        if mentions:
            placeholders = ','.join('?' for _ in mentions)
            cursor.execute(f"SELECT userID, username FROM Users WHERE username IN ({placeholders})", mentions)
            mentioned_users = cursor.fetchall()
            
            for user in mentioned_users:
                cursor.execute("INSERT INTO Comment_Mentions (CommentID, MentionedUserID) VALUES (?, ?)", (comment_id, user.userID))
                notification_link = url_for('workitems_overview', search=barcode, _external=False)
                create_notification(user.userID, f"{session['username']} mentioned you on barcode {barcode}", link=notification_link, icon='fa-at')

        conn.commit()
        log_user_action('addWorkitemComment', status='SUCCESS', resource_id=barcode)
        return jsonify({'success': True, 'message': _("Comment added.")})
    except Exception as e:
        app.logger.error(f"Error adding comment for barcode {barcode}: {e}")
        log_user_action('addWorkitemComment', status='FAILURE', resource_id=barcode, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/assign', methods=['POST'])
def assign_workitem(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    assignedUserID = data.get('assignedUserID')
    if assignedUserID is None:
        return jsonify({'success': False, 'message': _("Invalid assignment.")}), 400
    elif assignedUserID == 'None':
        assignedUserID = None
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("""
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETUTCDATE())) AS source (Barcode, AssignedUserID, UserID, UpdateTime)
            ON target.Barcode = source.Barcode
            WHEN MATCHED THEN
                UPDATE SET AssignedUserID = source.AssignedUserID, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (Barcode, AssignedUserID, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.Barcode, source.AssignedUserID, source.UserID, source.UpdateTime);
        """, (barcode, assignedUserID, session['userid']))
        
        conn.commit()
        log_user_action('assignUserToWorkitem', status='SUCCESS', resource_id=barcode, details={'assignedUserID': assignedUserID})
        if assignedUserID != None and assignedUserID != session['userid']:
            notification_link = url_for('workitems_overview', search=barcode, _external=False)
            create_notification(assignedUserID, f"{session['username']} {_('assigned you on barcode')} {barcode}", link=notification_link, icon='fa-people-carry-box')
        return jsonify({'success': True, 'message': _("Assignment updated.")})
    except Exception as e:
        app.logger.error(f"Error setting assignment for barcode {barcode}: {e}")
        log_user_action('assignUserToWorkitem', status='FAILURE', resource_id=barcode, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/priority', methods=['POST'])
def set_workitem_priority(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    priority = data.get('priority')
    if priority is None or priority not in [0, 1, 2, 3]:
        return jsonify({'success': False, 'message': _("Invalid priority level.")}), 400

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("""
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETUTCDATE())) AS source (Barcode, Priority, UserID, UpdateTime)
            ON target.Barcode = source.Barcode
            WHEN MATCHED THEN
                UPDATE SET Priority = source.Priority, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (Barcode, Priority, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.Barcode, source.Priority, source.UserID, source.UpdateTime);
        """, (barcode, priority, session['userid']))
        
        conn.commit()
        log_user_action('setWorkitemPriority', status='SUCCESS', resource_id=barcode, details={'priority': priority})
        return jsonify({'success': True, 'message': _("Priority updated.")})
    except Exception as e:
        app.logger.error(f"Error setting priority for barcode {barcode}: {e}")
        log_user_action('setWorkitemPriority', status='FAILURE', resource_id=barcode, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/tags')
def get_all_tags():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
        tags = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(tags)
    except Exception as e:
        app.logger.error(f"Failed to fetch all tags: {e}")
        return jsonify({"error": _("Could not fetch tags")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/tags', methods=['POST'])
def add_tag_to_workitem(barcode):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    tag_name = data.get('tagName', '').strip()
    tag_color = data.get('tagColor', '#6B7280') 

    if not tag_name:
        return jsonify({'success': False, 'message': _("Tag name cannot be empty.")}), 400

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute("SELECT TagID FROM Tags WHERE TagName = ?", (tag_name,))
        tag = cursor.fetchone()
        
        if tag:
            tag_id = tag.TagID
        else:
            cursor.execute("INSERT INTO Tags (TagName, TagColor, CreatedByUserID) OUTPUT INSERTED.TagID VALUES (?, ?, ?)",
                           (tag_name, tag_color, session['userid']))
            tag_id = cursor.fetchone().TagID
        
        cursor.execute("SELECT 1 FROM Workitem_Tags WHERE Barcode = ? AND TagID = ?", (barcode, tag_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': _("Workitem already has this tag.")}), 409

        cursor.execute("INSERT INTO Workitem_Tags (Barcode, TagID) VALUES (?, ?)", (barcode, tag_id))
        conn.commit()

        log_user_action('addWorkitemTag', status='SUCCESS', resource_id=barcode, details={'tagName': tag_name})
        return jsonify({'success': True, 'message': _("Tag added successfully."), 'tag': {'TagID': tag_id, 'TagName': tag_name, 'TagColor': tag_color}})

    except Exception as e:
        app.logger.error(f"Error adding tag to barcode {barcode}: {e}")
        log_user_action('addWorkitemTag', status='FAILURE', resource_id=barcode, details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/workitem/<barcode>/tags/<int:tag_id>', methods=['DELETE'])
def remove_tag_from_workitem(barcode, tag_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM Workitem_Tags WHERE Barcode = ? AND TagID = ?", (barcode, tag_id))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': _("Tag association not found.")}), 404

        log_user_action('removeWorkitemTag', status='SUCCESS', resource_id=barcode, details={'tagId': tag_id})
        return jsonify({'success': True, 'message': _("Tag removed successfully.")})
    except Exception as e:
        app.logger.error(f"Error removing tag {tag_id} from barcode {barcode}: {e}")
        log_user_action('removeWorkitemTag', status='FAILURE', resource_id=barcode, details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if conn:
            conn.close()
# ---------------------- workitem collaboration apis end --------------------- #

# --------------------------- workitem overview end -------------------------- #

def get_all_portal_users(access):
    conn = None
    try:
        conn_str = (f'DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_WEBPORTAL};UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;')
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        if access != 'Unlimited':
            cursor.execute("SELECT userID, fullname FROM Users ORDER BY fullname WHERE access = ?",access)  
        else:
            cursor.execute("SELECT userID, fullname FROM Users ORDER BY fullname")
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return users
    except Exception as e:
        app.logger.error(f"Failed to fetch all portal users: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ---------------------------------- profile --------------------------------- #
@app.route("/profile")
def profile():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        logged_in_user = session.get('username', 'Unknown')
        scope = session.get('scope', 'Unknown')
        subscription = session.get('subscription', 'Unknown')
        userid = session.get('userid', 'Unknown')
        fullname = session.get('fullname', 'Unknown')
        email = session.get('email', 'Unknown')
        company = session.get('company', 'Unknown')
        log_user_action('visitUserProfile', status='SUCCESS', resource_id='profile')
        return render_template("profile.html", userid=userid, logged_in_user=logged_in_user, scope=scope, fullname=fullname, email=email, company=company, subscription=subscription)
    except Exception as e:
        log_user_action('visitUserProfile', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

@app.route("/update_profile", methods=["POST", "GET"])
def update_profile():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        if request.method == "POST":
            userid = session['userid']
            username = session['username']
            fullname = request.form['fullName']
            email = request.form['email']
            company = request.form['company']

            if not re.search("(^[A-Za-z]{3,16})([ ]{0,1})([A-Za-z]{3,16})?([ ]{0,1})?([A-Za-z]{3,16})?([ ]{0,1})?([A-Za-z]{3,16})$", fullname) or len(fullname) >= 50:
                flash(_("Full name is not valid"), 'failure_updateProfile') 
                return redirect(url_for("profile"))
            if not re.search("^((?!\.)[\w\-_.]*[^.])(@\w+)(\.\w+(\.\w+)?[^.\W])$", email) or len(email) >= 50:
                flash(_("Email Adress is not valid"), 'failure_updateProfile') 
                return redirect(url_for("profile"))
            if not re.search("^\w[\w.\-#&\s]*$", company) or len(company) >= 50:
                flash(_("Company name is not valid"), 'failure_updateProfile') 
                return redirect(url_for("profile"))

            conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER_PRD},1433;'
                f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};'
                f'TrustServerCertificate=yes;'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE Users
                SET fullname = ?, email = ?, company = ?
                WHERE username = ?
            """, (fullname, email, company, username))
            
            conn.commit()
            cursor.close()
            conn.close()

            session['fullname'] = fullname
            session['email'] = email
            session['company'] = company

            if 'file' in request.files and request.files['file'].filename != '':
                f = request.files['file']
                try:
                    in_memory_file = io.BytesIO()
                    f.save(in_memory_file)
                    in_memory_file.seek(0)

                    img = Image.open(in_memory_file)
                    img.verify()

                    filename = f"{userid}-icon.png"
                    rel_path = os.path.join('static', 'images', filename)
                    abs_path = os.path.join(app.root_path, rel_path)
                    if os.path.exists(abs_path):
                        os.remove(abs_path)

                    in_memory_file.seek(0)
                    with open(abs_path, 'wb') as disk_file:
                        disk_file.write(in_memory_file.read())
                except Exception as e:
                    app.logger.error(f"Invalid image upload attempt by user {userid}: {e}")
                    flash(_("Invalid file format. Please upload a valid image."), 'failure_updateProfile')
                    return redirect(url_for("profile"))
                
            log_user_action(action_type='updateUserProfile', status='SUCCESS', resource_id='profile', details={
                "fullname": fullname,
                "email": email,
                "company": company
            })
            create_notification(userid, _("Your profile was updated successfully."), link=url_for('profile'), icon='fa-user-pen')
            flash(_("Profile updated successfully!"), 'success_updateProfile') 
            return redirect(url_for("profile"))
    except Exception as e:
        flash(_("Unexpected error"), 'failure_updateProfile') 
        log_user_action(action_type='updateUserProfile', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(url_for("profile"))

@app.route('/change_password',  methods=["POST", "GET"]) 
def change_password():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        
        if request.method == "POST":
            username = session['username']
            userid = session['userid']

            currentPassword = request.form['currentPassword'] 
            newPassword = request.form['newPassword']
            confirmPassword = request.form['confirmPassword']

            if newPassword != confirmPassword:
                flash('New passwords do not match', 'failure_changePW') 
                return redirect(url_for("profile"))        
            if not newPassword or not confirmPassword or not currentPassword:
                flash(_("All fields must be filled"), 'failure_changePW') 
                return redirect("profile")
            if not re.search('^\S{8,200}$', newPassword):
                flash(_("New password has to be atleast 8 characters long, with no whitespaces"), 'failure_changePW') 
                return redirect("profile")
            conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER_PRD},1433;'
                f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};'
                f'TrustServerCertificate=yes;'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                    SELECT password FROM Users WHERE username = ?
                """, username
            )
            row = cursor.fetchone()
            stored_hash = row[0]


            if isinstance(stored_hash, str):
                stored_hash = stored_hash.encode('utf-8')    

            if bcrypt.checkpw(currentPassword.encode('utf-8'), stored_hash):
                bytes = newPassword.encode('utf-8')
                salt = bcrypt.gensalt()
                hash = bcrypt.hashpw(bytes, salt)
                hash_str = hash.decode('utf-8')

                cursor.execute("""
                    UPDATE Users
                    SET password = ?
                    WHERE username = ?
                """, (hash_str, username))
                
                conn.commit()
                cursor.close()
                conn.close()

                create_notification(userid, _("Password updated successfully!"), link=url_for('profile'), icon='fa-user-shield')
                log_user_action(action_type='changeUserPassword', status='SUCCESS', resource_id='profile')
                flash(_("Password updated successfully!"), 'success_changePW') 
                return redirect("profile")
            else:
                flash(_("Current password is incorrect"), 'failure_changePW') 
                return redirect("profile")
    except Exception as e:
        flash(_("Unexpected Error"), 'failure_changePW') 
        log_user_action(action_type='changeUserPassword', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect("profile")

@app.route('/language/<lang>')
def set_language(lang=None):
    try:
        userid = session['userid']
        session['locale'] = lang
        create_notification(userid, _("Language changed successfully!"), link=url_for('profile'), icon='fa-language')
        log_user_action(action_type='changeUserLanguage', status='SUCCESS', resource_id='profile', details={"new_language": lang})
        flash(_("Language changed successfully!"), 'success_setLanguage')
        return redirect(request.referrer or url_for('index'))
    except Exception as e:
        flash(_("Unexpected Error"), 'failure_setLanguage')
        log_user_action(action_type='changeUserLanguage', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(request.referrer or url_for('index'))

@app.context_processor
def inject_current_lang():
    return {'current_lang': str(get_locale())}
# -------------------------------- profile end ------------------------------- #

# ---------------------------------- jdvance --------------------------------- #
@app.route('/jdvance')
@admin_required
def jdvance():
    return render_template("jd/jdvance.html")
# -------------------------------- jdvance end ------------------------------- #

# ---------------------------------- reports --------------------------------- #
@app.route("/reports")
def reports():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        userid = session['userid']
        scope = session['scope']

        process_name = request.args.get('processFilterReports', 'both')
        session['process_name_reports'] = process_name

        log_user_action(action_type='visitReports', status='SUCCESS', resource_id='reports')
        return render_template("reports.html", userid=userid, scope=scope, process_name=process_name)
    except Exception as e:
        log_user_action(action_type='visitReports', status='FAILURE', resource_id='reports', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

# ---- replace the current /api/reports/processed_over_time with this version ----
@app.route("/api/reports/processed_over_time")
def report_processed_over_time():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    # read customization options (all optional & backwards compatible)
    start_str = request.args.get('startDate')   # ISO 8601: "2025-10-01"
    end_str   = request.args.get('endDate')     # ISO 8601
    group_by  = (request.args.get('groupBy') or 'day').lower()  # day|week|month
    statuses_q = request.args.get('statuses')   # e.g., "Done" or "Ready,In Progress,Done"
    process_override = request.args.get('processFilterReports')

    # fall back to session process filter (existing behaviour)
    process_name = process_override or session.get('process_name_reports', 'both')
    placeholders, proc_params = get_process_filter_and_params(process_name)
    all_params = proc_params + ['Privera']

    # map status names -> codes used in DB (0=Ready,1=In Progress,5=Done)
    name_to_code = {'ready': 0, 'in progress': 1, 'done': 5}
    status_codes = None
    if statuses_q:
        status_codes = [name_to_code[s.strip().lower()] for s in statuses_q.split(',') if s.strip().lower() in name_to_code]

    # default window: last 30 days (existing behaviour)
    # allow custom start/end
    date_filter_sql = "twi.ModifiedAt >= DATEADD(day, -30, GETDATE())"
    date_params = []
    if start_str:
        date_filter_sql = "twi.ModifiedAt >= ?"
        date_params.append(datetime.fromisoformat(start_str))
    if end_str:
        # inclusive end -> use < end + 1 day, or cast as date; keep simple with < end
        if start_str:
            date_filter_sql = "twi.ModifiedAt >= ? AND twi.ModifiedAt < ?"
            date_params.append(datetime.fromisoformat(end_str))
        else:
            date_filter_sql = "twi.ModifiedAt < ?"
            date_params.append(datetime.fromisoformat(end_str))

    # grouping key
    if group_by == 'week':
        group_key = "CONCAT(DATENAME(iso_week, DATEADD(HOUR,2,twi.ModifiedAt)), '/', DATEPART(year, DATEADD(HOUR,2,twi.ModifiedAt)))"
        order_key = "MIN(CAST(DATEADD(HOUR,2,twi.ModifiedAt) AS DATE))"
    elif group_by == 'month':
        group_key = "FORMAT(DATEADD(HOUR,2,twi.ModifiedAt), 'yyyy-MM')"
        order_key = "MIN(CAST(DATEADD(HOUR,2,twi.ModifiedAt) AS DATE))"
    else:  # day
        group_key = "CAST(DATEADD(HOUR,2,twi.ModifiedAt) AS DATE)"
        order_key = "CAST(DATEADD(HOUR,2,twi.ModifiedAt) AS DATE)"

    # status filter (default used to be Done only)
    status_sql = "twi.Status = 5"
    status_params = []
    if status_codes:
        placeholders_status = ','.join(['?'] * len(status_codes))
        status_sql = f"twi.Status IN ({placeholders_status})"
        status_params = status_codes

    conn = None
    try:
        conn_str = (
            f"DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_RUNTIME};"
            f"UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT 
                {group_key} AS Bucket,
                COUNT(twi.ID) as ItemCount,
                {order_key} as SortKey
            FROM t_WorkItems twi
            LEFT JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID 
            LEFT JOIN t_Processes tp ON tp.ID = tai.ProcessID
            WHERE tp.Name IN ({placeholders})
              AND tp.ClientName = ?
              AND {status_sql}
              AND {date_filter_sql}
            GROUP BY {group_key}
            ORDER BY SortKey;
        """, *(all_params + status_params + date_params))
        rows = cursor.fetchall()

        labels = [row.Bucket for row in rows]
        data = [row.ItemCount for row in rows]
        return jsonify({'labels': labels, 'data': data})
    except Exception as e:
        app.logger.error(f"Failed to fetch processed_over_time report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# ---- replace /api/reports/status_distribution with this version ----
@app.route("/api/reports/status_distribution")
def report_status_distribution():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    start_str = request.args.get('startDate')
    end_str   = request.args.get('endDate')
    statuses_q = request.args.get('statuses')  # optional
    process_override = request.args.get('processFilterReports')

    process_name = process_override or session.get('process_name_reports', 'both')
    placeholders, proc_params = get_process_filter_and_params(process_name)
    all_params = proc_params + ['Privera']

    name_to_code = {'ready':0,'in progress':1,'done':5}
    status_codes = [0,1,5]
    if statuses_q:
        status_codes = [name_to_code[s.strip().lower()] for s in statuses_q.split(',') if s.strip().lower() in name_to_code]

    # If date window provided, compute counts within the window; else use your fast absolute helper.
    if not start_str and not end_str and set(status_codes)=={0,1,5}:
        stats = get_absolute_dashboard_stats(process_name)  # existing behaviour
        labels = ['Ready','In Progress','Done','Backlog']
        data = [
            stats.get('ReadyTotal',0),
            stats.get('InProgressTotal',0),
            stats.get('DoneTotal',0),
            stats.get('BacklogTotal',0)
        ]
        return jsonify({'labels': labels, 'data': data})

    date_sql = "1=1"
    date_params = []
    if start_str:
        date_sql = "twi.ModifiedAt >= ?"
        date_params.append(datetime.fromisoformat(start_str))
    if end_str:
        date_sql = ("twi.ModifiedAt >= ? AND twi.ModifiedAt < ?") if start_str else "twi.ModifiedAt < ?"
        if not start_str:
            date_params = []
        date_params.append(datetime.fromisoformat(end_str))

    conn = None
    try:
        conn_str = (
            f"DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_RUNTIME};"
            f"UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Count Ready / In Progress / Done inside the window
        placeholders_status = ','.join(['?']*len(status_codes))
        cursor.execute(f"""
            WITH Mapped AS (
              SELECT 
                CASE WHEN twi.Status = 0 THEN 'Ready'
                     WHEN twi.Status = 1 THEN 'In Progress'
                     WHEN twi.Status = 5 THEN 'Done'
                     ELSE 'Other' END as S
              FROM t_WorkItems twi
              LEFT JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID 
              LEFT JOIN t_Processes tp ON tp.ID = tai.ProcessID
              WHERE tp.Name IN ({placeholders})
                AND tp.ClientName = ?
                AND twi.Status IN ({placeholders_status})
                AND {date_sql}
            )
            SELECT S, COUNT(*) Cnt FROM Mapped WHERE S <> 'Other' GROUP BY S;
        """, *(all_params + status_codes + date_params))
        counts = {'Ready':0,'In Progress':0,'Done':0}
        for s,c in cursor.fetchall():
            counts[s] = c

        # Backlog unchanged (it's a system total), keep your existing backlog count:
        stats_abs = get_absolute_dashboard_stats(process_name)

        return jsonify({
            'labels': ['Ready','In Progress','Done','Backlog'],
            'data': [counts['Ready'], counts['In Progress'], counts['Done'], stats_abs.get('BacklogTotal',0)]
        })
    except Exception as e:
        app.logger.error(f"Failed to fetch status_distribution report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/reports/kpi_stats")
def report_kpi_stats():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    conn = None

    placeholders, params = get_process_filter_and_params(session['process_name_reports'])
    all_params = params + ['Privera']

    try:
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={DB_SERVER_DB_RUNTIME};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT COUNT(twi.ID) FROM t_WorkItems twi
            LEFT JOIN t_Processes tp ON tp.ID = (SELECT ProcessID FROM t_ActivityInstances WHERE ID = twi.ActivityInstanceID)
            WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ? AND twi.Status = 5
            AND CAST(DATEADD(HOUR, 2, twi.ModifiedAt) AS DATE) = CAST(GETDATE() AS DATE);
        """,all_params)
        processed_today = cursor.fetchone()[0]
        
        window_days = int(request.args.get('windowDays', '7'))
        cursor.execute(F"""
            SELECT COUNT(twi.ID) FROM t_WorkItems twi
            LEFT JOIN t_Processes tp ON tp.ID = (SELECT ProcessID FROM t_ActivityInstances WHERE ID = twi.ActivityInstanceID)
            WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ? AND twi.Status = 5
            AND twi.ModifiedAt >= DATEADD(day, -?, GETDATE());
        """, *(all_params + [window_days]))
        processed_week = cursor.fetchone()[0]
        
        cursor.execute(f"""
            SELECT COUNT(*) FROM t_WorkItems w
            LEFT JOIN t_ActivityInstances a on a.id = w.ActivityInstanceID
            LEFT JOIN t_Processes p on p.id = a.ProcessID
            WHERE p.Name IN ({placeholders}) AND p.ClientName = ? AND a.ActivityInstanceName = 'C+A';
        """,all_params)
        current_backlog = cursor.fetchone()[0]
        
        return jsonify({
            'processed_today': processed_today,
            'processed_week': processed_week,
            'current_backlog': current_backlog
        })
        
    except Exception as e:
        app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# ---- replace /api/reports/stage_breakdown with this version ----
@app.route("/api/reports/stage_breakdown")
def report_stage_breakdown():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401

    start_str = request.args.get('startDate')
    end_str   = request.args.get('endDate')
    statuses_q = request.args.get('statuses')
    process_override = request.args.get('processFilterReports')

    process_name = process_override or session.get('process_name_reports', 'both')
    placeholders, proc_params = get_process_filter_and_params(process_name)
    all_params = proc_params + ['Privera']

    name_to_code = {'ready':0,'in progress':1,'done':5}
    status_codes = [0,1]  # previously excluded Done/Deleted -> keep default; include Done if requested
    if statuses_q:
        status_codes = [name_to_code[s.strip().lower()] for s in statuses_q.split(',') if s.strip().lower() in name_to_code]

    date_sql = "1=1"
    date_params = []
    if start_str:
        date_sql = "twi.ModifiedAt >= ?"
        date_params.append(datetime.fromisoformat(start_str))
    if end_str:
        date_sql = ("twi.ModifiedAt >= ? AND twi.ModifiedAt < ?") if start_str else "twi.ModifiedAt < ?"
        if not start_str:
            date_params = []
        date_params.append(datetime.fromisoformat(end_str))

    conn = None
    try:
        conn_str = (
            f"DRIVER={{SQL Server}};SERVER={DB_SERVER_PRD},1433;DATABASE={DB_SERVER_DB_RUNTIME};"
            f"UID={DB_UID};PWD={DB_PWD};TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        placeholders_status = ','.join(['?']*len(status_codes))
        cursor.execute(f"""
           SELECT 
                CASE
                    WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'In Validation'
                    WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'In Export'
                    WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'In Import'
                    WHEN tai.ActivityInstanceName LIKE '%Extract%' THEN 'In Extraction'
                    WHEN tai.ActivityInstanceName LIKE '%OCR%' THEN 'In OCR'
                    WHEN tai.ActivityInstanceName LIKE '%Statistik%' THEN 'DB Saving'
                    WHEN tai.ActivityInstanceName LIKE '%Collect%' THEN 'Collecting'
                    ELSE 'Processing'
                END AS Activity,
                COUNT(twi.ID) as ItemCount
            FROM t_WorkItems twi 
            LEFT JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID 
            LEFT JOIN t_Processes tp ON tp.ID = tai.ProcessID
            WHERE tp.Name IN ({placeholders})
              AND tp.ClientName = ?
              AND twi.Status IN ({placeholders_status})
              AND tai.ActivityInstanceName NOT LIKE '%Pause%'
              AND {date_sql}
            GROUP BY 
                CASE
                    WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'In Validation'
                    WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'In Export'
                    WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'In Import'
                    WHEN tai.ActivityInstanceName LIKE '%Extract%' THEN 'In Extraction'
                    WHEN tai.ActivityInstanceName LIKE '%OCR%' THEN 'In OCR'
                    WHEN tai.ActivityInstanceName LIKE '%Statistik%' THEN 'DB Saving'
                    WHEN tai.ActivityInstanceName LIKE '%Collect%' THEN 'Collecting'
                    ELSE 'Processing'
                END
            ORDER BY ItemCount DESC;
        """, *(all_params + status_codes + date_params))

        rows = cursor.fetchall()
        labels = [row.Activity for row in rows]
        data = [row.ItemCount for row in rows]
        return jsonify({'labels': labels, 'data': data})
    except Exception as e:
        app.logger.error(f"Failed to fetch stage_breakdown report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()
# -------------------------------- reports end ------------------------------- #

# ------------------------------- error handler ------------------------------ #
@app.errorhandler(404)
def page_not_found(e):
    return render_template("handlers/404.html"), 404

@app.errorhandler(500)
def internalError(e):
    return render_template("handlers/500.html"), 500

@app.errorhandler(403)
def forbiddenPage(e):
    return render_template('handlers/403.html'), 403
# ----------------------------- error handler end ---------------------------- #

# ------------------------------- ONLY FOR IIS ------------------------------- #
#  app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/nexora')
# ----------------------------- ONLY FOR IIS end ----------------------------- #


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)