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
from werkzeug.exceptions import HTTPException
import pyotp
import qrcode
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman
import magic  
from sqlalchemy import create_engine, pool
import urllib

# -------------------------------- app config -------------------------------- #
app = Flask(__name__)
load_dotenv()

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

class PermissionDenied(HTTPException):
    code = 403
    description = "Forbidden"

@app.errorhandler(PermissionDenied)
def handle_permission_denied(e):
    return render_template('handlers/403.html'), 403
# ----------------------------- error handler end ---------------------------- #

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

csrf = CSRFProtect(app)
# csp = {
#     'default-src': '\'self\'',
#     'script-src': [
#         '\'self\'',
#         '\'unsafe-inline\'',             
#         'https://cdn.tailwindcss.com',   
#         'https://cdnjs.cloudflare.com',  
#         'https://cdn.jsdelivr.net'       
#     ],
#     'style-src': [
#         '\'self\'',
#         '\'unsafe-inline\'',             
#         'https://fonts.googleapis.com',  
#         'https://cdnjs.cloudflare.com',
#         'https://cdn.jsdelivr.net'
#     ],
#     'font-src': [
#         '\'self\'',
#         'https://fonts.gstatic.com',     
#         'https://cdnjs.cloudflare.com'
#     ],
#     'img-src': [
#         '\'self\'',
#         'data:',
#         'blob:',                         
#         'https://cdn.tailwindcss.com'
#     ],
#     'connect-src': [
#         '\'self\'',                     
#         'https://cdn.tailwindcss.com',
#         'https://cdnjs.cloudflare.com',
#         'https://cdn.jsdelivr.net'
#     ]
# }
# Talisman(app, content_security_policy=csp)


DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER_PRD = os.environ.get("DB_SERVER_PRD")
DB_NEXORA = os.environ.get("DB_NEXORA")
DB_STATISTICS = os.environ.get("DB_STATISTICS")
DB_OCTO_RUNTIME = os.environ.get("DB_OCTO_RUNTIME")
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
OCTO_CLIENT_SECRET = os.environ.get("OCTO_CLIENT_SECRET")
OCTO_CLIENT_ID = os.environ.get("OCTO_CLIENT_ID")
OCTO_GRANT_TYPE = os.environ.get("OCTO_GRANT_TYPE")
BEXIO_PAT = os.environ.get("BEXIO_PAT")
BEXIO_PRIVERA_CLIENT_ID = os.environ.get("BEXIO_PRIVERA_CLIENT_ID")



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


# ------------------------------ database connection ------------------------- #
def getDBUrl(d):
    params = urllib.parse.quote_plus(
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER_PRD},1433;'
            f'DATABASE={d};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
        )
    return f"mssql+pyodbc:///?odbc_connect={params}"

engineOctoDB = create_engine(
    getDBUrl(DB_OCTO_RUNTIME),
    pool_size=10, 
    max_overflow=20,
    pool_timeout=30,  
    pool_recycle=1800 
)
engineNexoraDB = create_engine(
    getDBUrl(DB_NEXORA),
    pool_size=10, 
    max_overflow=20,
    pool_timeout=30,  
    pool_recycle=1800 
)
engineStatisticsDB = create_engine(
    getDBUrl(DB_STATISTICS),
    pool_size=10, 
    max_overflow=20,
    pool_timeout=30,  
    pool_recycle=1800 
)
# ------------------------------ database connection end --------------------- #


# ---------------------------------- logging --------------------------------- #
def log_user_action(action_type, status, target_user_id=None, resource_id=None, details=None, IsInternalError=0):
    if 'username' not in session:
        return
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO User_Logs
            (SessionID, UserID, Username, ActionType, ActionStatus, TargetUserID, TargetResourceID, Details, IPAddress, UserAgent, IsInternalError)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get('uuid'),
            session.get('userid'),
            session.get('username'),
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

def load_permissions_for_user(user_id):
    conn = engineNexoraDB.raw_connection()
    cur = conn.cursor()
    cur.execute("EXEC dbo.spGetUserPermissions ?", user_id)
    perms = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return perms

def has_permission(code: str) -> bool:
    perms = set(session.get('permissions', []))
    # print('requestedcode:',code,code in perms, '\n\n')
    return code in perms

def require_permission(code):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            if not has_permission(code):
                raise PermissionDenied()
            return f(*args, **kwargs)
        return wrapper
    return decorator

def pageVisability():
    adminPagePerm = has_permission('admin.view')
    dashboardPagePerm = has_permission('dashboard.view')
    workitemsPagePerm = has_permission('workitems.view')
    teamboardPagePerm = has_permission('teamboard.view')
    invoicesPagePerm = has_permission('invoices.view')
    return {'adminPagePerm': adminPagePerm, 'dashboardPagePerm': dashboardPagePerm, 
            'workitemsPagePerm':workitemsPagePerm, 'teamboardPagePerm': teamboardPagePerm,
            'invoicesPagePerm': invoicesPagePerm}

@app.route('/init_2FA', methods=['GET', 'POST'])
def init_2FA():
    if 'pre_2fa_userid' not in session:
        return redirect(url_for('login'))
    user_id = session['pre_2fa_userid']

    if request.method == 'GET':
        secret = pyotp.random_base32()
        
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=session.get('pre_2fa_username', 'User'), 
            issuer_name='nexora'
        )
        
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        qr_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        session['temp_2fa_secret'] = secret
        return render_template('init_2FA.html', qr_code=qr_b64, secret=secret)

    elif request.method == 'POST':
        code = request.form.get('code')
        secret = session.get('temp_2fa_secret')

        if not code or not secret:
            flash(_("Session expired, please try again"), "error")
            return redirect(url_for('init_2FA'))

        totp = pyotp.TOTP(secret)
        if totp.verify(code):
            try:
                conn = engineNexoraDB.raw_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE Users 
                    SET twoFA = 1, TwoFASecret = ? 
                    WHERE userid = ?
                """, (secret, user_id))
                conn.commit()
                
                session.pop('temp_2fa_secret', None)
                create_notification(user_id, _("2FA enabled successfully"), icon='fa-shield-halved')
                return redirect(url_for('dashboard'))
            except Exception as e:
                app.logger.error(f"2FA Setup DB Error: {e}")
                return render_template('init_2FA.html', error=_("Database error"))
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

        else:
            flash(_("Invalid code. Please try again."), "error")
            return redirect(url_for('init_2FA'))
    

@app.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'pre_2fa_userid' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'GET':
        return render_template('verify_2fa.html') 

    elif request.method == 'POST':
        code = request.form.get('code')
        user_id = session['pre_2fa_userid']

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TwoFASecret, username, fullname, email, organizationcode FROM Users WHERE userid = ?", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return redirect(url_for('login'))

        secret, username, fullname, email, org_code = row

        totp = pyotp.TOTP(secret)
        if totp.verify(code):
            session.clear() 
            session['userid'] = user_id
            session['username'] = username
            session['fullname'] = fullname
            session['email'] = email
            session['organizationcode'] = org_code
            session['uuid'] = uuid.uuid4()
            session['permissions'] = load_permissions_for_user(str(user_id))
            
            log_user_action(action_type='logUserIn_2FA', status='SUCCESS', resource_id='login')
            return redirect(url_for('dashboard'))
        else:
            flash(_("Invalid code"), "error")
            return render_template('verify_2fa.html')
        


@app.route('/init_reset')
def init_reset():
    return render_template('init_reset.html')

@app.route('/init_reset_password',methods=['POST', 'GET'])
def init_reset_password():
    try:
        new_password = request.form['new-password']
        confirm_password = request.form['confirm-password']
        pre_auth_userid = session.get('pre_auth_userid')
        if new_password != confirm_password:
            return render_template("init_reset.html", error=_("Passwords do not match"))
        if not new_password or not confirm_password:
            return render_template("init_reset.html", error=_("All Fields must be filled"))
        if not re.search('^\S{8,200}$', new_password):
            return render_template("init_reset.html", error=_("New password has to be atleast 8 characters long, with no whitespaces"))

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
                SELECT password, twoFA, username FROM Users WHERE userid = ?
            """, pre_auth_userid
        )
        row = cursor.fetchone()
        stored_hash = row[0]
        stored_2FA = row[1]
        stored_username = row[2]

        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')

        if bcrypt.checkpw(new_password.encode('utf-8'), stored_hash):
            return render_template("init_reset.html", error=_("New Password musn't be previously used password"))

        bytes = new_password.encode('utf-8')
        salt = bcrypt.gensalt()
        hash = bcrypt.hashpw(bytes, salt)
        hash_str = hash.decode('utf-8')

        cursor.execute("""
            UPDATE Users
            SET password = ?, initReset = 1
            WHERE userid = ?
        """, (hash_str, pre_auth_userid))

        conn.commit()
        cursor.close()
        conn.close()

        create_notification(pre_auth_userid, _("Initial Password changed successfully"), link=url_for('profile'), icon='fa-unlock')
        log_user_action(action_type='InitResetUserPassword', status='SUCCESS', resource_id='initResetPassword')
        if not stored_2FA:
            session['pre_2fa_userid'] = pre_auth_userid
            session['pre_2fa_username'] = stored_username 
            return redirect(url_for('init_2FA'))
        else:
            return redirect(url_for('login'))
    except Exception as e:
        log_user_action(action_type='InitResetUserPassword', status='FAILURE', resource_id='initResetPassword', details={"serverError": str(e)}, IsInternalError=1)
        return

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        # DEV ONLY!!!
        if UID_REQUEST == '123' and PWD_REQUEST == '123':
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT username, fullname, email, organizationcode FROM Users WHERE userid = 1019")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            username, fullname, email, org_code = row

            session.clear() 
            session['userid'] = "1019"
            session['username'] = username
            session['fullname'] = fullname
            session['email'] = email
            session['organizationcode'] = org_code
            session['uuid'] = uuid.uuid4()
            session['permissions'] = load_permissions_for_user("1019")
            
            log_user_action(action_type='logUserIn_2FA', status='SUCCESS', resource_id='login')
            return redirect(url_for('dashboard'))
        if not UID_REQUEST or not PWD_REQUEST:
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"clientError": "Invalid credentials"})
            return render_template('index.html', error=_("Invalid credentials"))

        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT userid, password, username, initreset, twoFA FROM Users WHERE username = ?
            """, (UID_REQUEST,))
            user_record = cursor.fetchone()

            if user_record:
                stored_userid = user_record[0]
                stored_hash = user_record[1]
                stored_username = user_record[2]
                stored_initReset = user_record[3]
                stored_2FA = user_record[4]

                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')

                if bcrypt.checkpw(PWD_REQUEST.encode('utf-8'), stored_hash):
                    if not stored_initReset:
                        session['pre_auth_userid'] = str(stored_userid)
                        return redirect(url_for("init_reset"))
                    if not stored_2FA:
                        session['pre_2fa_userid'] = str(stored_userid)
                        session['pre_2fa_username'] = stored_username
                        return redirect(url_for("init_2FA"))
                    else:
                        session.clear()
                        session['pre_2fa_userid'] = str(stored_userid) 
                        session['pre_2fa_username'] = stored_username 
                        return redirect(url_for('verify_2fa'))
           
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"clientError": "Invalid credentials"})
            return render_template('index.html', error=_("Invalid credentials"))

        except Exception as e:
            log_user_action(action_type='logUserIn', status='FAILURE', resource_id='login', details={"serverError": str(e)}, IsInternalError=1)
            app.logger.error(f"Database error during login: {e}")
            return render_template('index.html', error=_("Login temporarily unavailable"))
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template('index.html')

# ----------------------------- session login end ---------------------------- #

# ------------------------------- notifications ------------------------------ #
def create_notification(user_id, message, link=None, icon='fa-info-circle'):
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Notifications (UserID, Message, Link, Icon)
            VALUES (?, ?, ?, ?)
        """, (user_id, message, link, icon))
        conn.commit()
    except Exception as e:
        app.logger.error(f"Failed to create notification for UserID {user_id}: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/notifications")
def get_notifications():
    if 'userid' not in session:
        return jsonify({"error": _("Not authenticated")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
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
        if cursor:
            cursor.close()
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
        conn = engineNexoraDB.raw_connection()
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
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ----------------------------- notifications end ---------------------------- #

# ----------------------------------- admin ---------------------------------- #
@app.route("/admin")
@require_permission('admin.view')
def admin_dashboard():
    if 'username' not in session:
        return redirect(url_for("login"))
    return render_template("admin/adminOverview.html", 
                         logged_in_user=session.get('username'), 
                         userid=session.get('userid'), pageV=pageVisability())


@app.route("/admin/organizations")
@require_permission('admin.view')
def admin_organizations_view():
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            select organizationcode, organization from organizations 
        """)
        organizations = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        return render_template("admin/organizations.html",organizations=organizations, logged_in_user=session.get('username'),userid=session.get('userid'), pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Failed to fetch organizations: {e}")
        return render_template('500.html')
    finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

@app.route("/admin/organizations/add", methods=['POST'])
@require_permission('admin.add.organization')
def admin_add_organization():
    data = request.get_json()
    organization = data.get('organizationname')
    userid = session['userid']

    if not organization:
        return jsonify({'success': False, 'message': _("All fields are required.")}), 400

    clean_name = re.sub(r'[^A-Z0-9]', '', organization.upper())

    consonants = re.sub(r'[AEIOU]', '', clean_name)
    vowels = re.sub(r'[^AEIOU]', '', clean_name)
    code = (consonants + vowels)
    organizationcode = code[:4].ljust(4, 'X')

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO organizations VALUES(?,?)", (organizationcode, organization,))
        conn.commit()

        create_notification(userid, _("Organization created successfully.") , link=url_for('admin_organizations_view'), icon='fa-square-plus')
        log_user_action('createNewOrganizationAdmin', status='SUCCESS', resource_id='visitOrganizationManagement',details={'newOrganization': organization})
        return jsonify({'success': True, 'message': _("Organization created successfully.")})
    except pyodbc.IntegrityError:
        log_user_action('createNewOrganizationAdmin', status='FAILURE', resource_id='visitOrganizationManagement', details={"adminError": "Organization already exists", 'newOrganization': organization})
        return jsonify({'success': False, 'message': _("Organization already exists.")}), 409
    except Exception as e:
        app.logger.error(f"Error adding organization: {e}")
        log_user_action('createNewOrganizationAdmin', status='FAILURE', resource_id='visitOrganizationManagement', details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/organizations/edit/<organizationcode>", methods=['POST'])
@require_permission('admin.edit.organization')
def admin_edit_organization(organizationcode):
    data = request.get_json()
    organization = data.get('organizationname')
    currentUserId = session['userid']

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE organizations SET organization=? WHERE organizationcode=?",
                        (organization, organizationcode))
        conn.commit()
        
        create_notification(currentUserId, _("Organization updated successfully"), link=url_for('admin_organizations_view'), icon='fa-pen')
        log_user_action('editOrganizationAdmin', status='SUCCESS', resource_id='visitOrganizationManagement')
        return jsonify({'success': True, 'message': _("Organization updated successfully.")})
    except Exception as e:
        app.logger.error(f"Error editing Organization {currentUserId}: {e}")
        log_user_action('editOrganizationAdmin', status='FAILURE', resource_id='visitOrganizationManagement', details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/organizations/delete/<organizationcode>", methods=['DELETE'])
@require_permission('admin.delete.organization')
def admin_delete_organization(organizationcode):
    current_user = session.get('userid')

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM organizations WHERE organizationcode=?", (organizationcode,))
        conn.commit()

        if cursor.rowcount == 0:
            log_user_action('deleteOrganizationAdmin', status='FAILURE', details={'adminError': 'Organization not found'}, resource_id='visitOrganizationManagement')
            return jsonify({'success': False, 'message': _("Organization not found.")}), 404

        create_notification(current_user, _("Organization deleted successfully"), link=url_for('admin_organizations_view'), icon='fa-slash')
        
        log_user_action('deleteOrganizationAdmin', status='SUCCESS', resource_id='visitOrganizationManagement')
        return jsonify({'success': True, 'message': _("Organization deleted successfully.")})
    except Exception as e:
        app.logger.error(f"Error deleting Organization {organizationcode}: {e}")
        log_user_action('deleteOrganizationAdmin', status='FAILURE', resource_id='visitOrganizationManagement', details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/users")
@require_permission('admin.view')
def admin_users():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT userID, username, fullname, email, ap.name accessprofile, o.organization organization FROM Users u
            join accessprofile ap on ap.accessid = u.accessid
            join organizations o on o.organizationcode = u.organizationcode 
            ORDER BY username
        """)
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        cursor.execute("SELECT ap.name profile, ap.accessid accessid FROM accessprofile ap")
        accessprofiles =  [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        cursor.execute("SELECT organizationcode, organization FROM Organizations")
        organizations =  [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        return render_template("admin/userManagement.html",organizations=organizations, accessprofiles=accessprofiles, users=users, userid=session.get('userid'), logged_in_user=session.get('username'), pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Failed to fetch users: {e}")
        return render_template('500.html')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/logs")
@require_permission('admin.view')
def admin_logs_view():
    return render_template("admin/logs.html", logged_in_user=session.get('username'),userid=session.get('userid'), pageV=pageVisability())

@app.route("/api/admin/logs/search")
@require_permission('admin.view')
def api_admin_logs_search():
    username = request.args.get('username', '').strip()
    action_type = request.args.get('action_type', '').strip()
    status = request.args.get('status', '').strip()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    query_parts = ["1=1"]
    params = []

    if username:
        query_parts.append("Username LIKE ?")
        params.append(f"%{username}%")
    if action_type:
        query_parts.append("ActionType LIKE ?")
        params.append(f"%{action_type}%")
    if status:
        query_parts.append("ActionStatus = ?")
        params.append(status)
    if start_date:
        query_parts.append("Timestamp >= ?")
        params.append(start_date)
    if end_date:
        query_parts.append("Timestamp <= ?")
        params.append(f"{end_date} 23:59:59")

    where_clause = " AND ".join(query_parts)

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT COUNT(*) FROM User_Logs WHERE {where_clause}", params)
        total_count = cursor.fetchone()[0]

        sql = f"""
            SELECT LogID, Timestamp, Username, ActionType, ActionStatus, Details, IPAddress 
            FROM User_Logs 
            WHERE {where_clause}
            ORDER BY Timestamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(sql, params + [offset, per_page])
        logs = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        return jsonify({
            "logs": logs,
            "total": total_count,
            "page": page,
            "pages": math.ceil(total_count / per_page)
        })
    except Exception as e:
        app.logger.error(f"Log search error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/sessions")
@require_permission('admin.view')
def admin_sessions_view():
    return render_template("admin/sessions.html", logged_in_user=session.get('username'), userid=session.get('userid'), pageV=pageVisability())

@app.route("/admin/users/add", methods=['POST'])
@require_permission('admin.create.user')
def admin_add_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    fullname = data.get('fullname')
    email = data.get('email')
    organization = data.get('organization')
    accessprofile = data.get('accessprofile')
    userid = session['userid']


    if not all([username, password, fullname, email, organization, accessprofile]):
        return jsonify({'success': False, 'message': _("All fields are required.")}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessid = cursor.fetchone()[0]
        cursor.execute("select organizationcode from organizations where organization = ?", organization)
        organizationcode = cursor.fetchone()[0]
        cursor.execute("INSERT INTO Users (username, password, fullname, email, organizationcode, accessid) VALUES (?, ?, ?, ?, ?, ?)",
                       (username, hashed_password, fullname, email, organizationcode, accessid))
        conn.commit()
        create_notification(userid, _("User created successfully.") , link=url_for('admin_users'), icon='fa-user-plus')
        log_user_action('createNewUserAdmin', status='SUCCESS', resource_id='visitUserManagement',details={'newUsername': username})
        return jsonify({'success': True, 'message': _("User created successfully.")})
    except pyodbc.IntegrityError:
        log_user_action('createNewUserAdmin', status='FAILURE', resource_id='visitUserManagement', details={"adminError": "Username or email already exists", 'newUsername': username})
        return jsonify({'success': False, 'message': _("Username or email already exists.")}), 409
    except Exception as e:
        app.logger.error(f"Error adding user: {e}")
        log_user_action('createNewUserAdmin', status='FAILURE', resource_id='visitUserManagement', details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/users/edit/<int:user_id>", methods=['POST'])
@require_permission('admin.edit.user')
def admin_edit_user(user_id):
    data = request.get_json()
    username = data.get('username')
    fullname = data.get('fullname')
    email = data.get('email')
    password = data.get('password')
    organization = data.get('organization')
    accessprofile = data.get('accessprofile')
    currentUserId = session['userid']

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("select accessid from accessprofile where name = ?", accessprofile)
        accessid = cursor.fetchone()[0]
        cursor.execute("select organizationcode from organizations where organization = ?", organization)
        organizationcode = cursor.fetchone()[0]

        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute("UPDATE Users SET username=?, fullname=?, email=?, password=?, organizationcode=?,accessid=? WHERE userID=?",
                           (username, fullname, email, hashed_password, organizationcode,accessid, user_id))
        else:
            cursor.execute("UPDATE Users SET username=?, fullname=?, email=?,  organizationcode=?,accessid=? WHERE userID=?",
                           (username, fullname, email, organizationcode, accessid, user_id))
        conn.commit()

        create_notification(currentUserId, _("User updated successfully"), link=url_for('admin_users'), icon='fa-user-pen')
        log_user_action('editUserAdmin', status='SUCCESS', resource_id='visitUserManagement', target_user_id=user_id)
        return jsonify({'success': True, 'message': _("User updated successfully.")})
    except Exception as e:
        app.logger.error(f"Error editing user {user_id}: {e}")
        log_user_action('editUserAdmin', status='FAILURE', resource_id='visitUserManagement', target_user_id=user_id, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/admin/users/delete/<int:user_id>", methods=['DELETE'])
@require_permission('admin.delete.user')
def admin_delete_user(user_id):
    current_user = session.get('userid')
    if str(user_id) == current_user:
        log_user_action('deleteUserAdmin', status='FAILURE', target_user_id=user_id, details={'adminError': 'Self-delete attempt'}, resource_id='visitUserManagement')
        return jsonify({'success': False, 'message': _("You cannot delete your own account.")}), 403

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("delete from tags where createdbyuserid = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from workitem_metadata where assigneduserid = ? or lastupdatedbyuserid = ?", (user_id,user_id,))
        cursor.commit()

        cursor.execute("delete from userpermissionoverride where userid = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from notifications where userid = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from comment_mentions where mentioneduserid = ?", (user_id,))
        cursor.commit()
        
        cursor.execute("delete from workitem_comments where userid = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from users where userid = ?", (user_id,))
        cursor.commit()

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
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/recent_logs")
@require_permission('admin.view')
def admin_recent_logs():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
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
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/active_sessions")
@require_permission('admin.view')
def admin_active_sessions():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
				Username,
				Userid,
                IPAddress,
                MAX(Timestamp) as LastActivity
            FROM User_Logs
            WHERE Timestamp >= DATEADD(minute, -30, getdate())
            GROUP BY SessionID, Username, IPAddress, Userid
            ORDER BY LastActivity DESC
        """)
        sessions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(sessions)
    except Exception as e:
        app.logger.error(f"Failed to fetch active sessions for admin panel: {e}")
        return jsonify({"error": _("Could not fetch sessions")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ----------------------------- Access Control ------------------------------ #

@app.route("/admin/access_control")
@require_permission('admin.view') 
def admin_access_control():
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT AccessID, Name, Description FROM AccessProfile ORDER BY Name")
        profiles = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        
        cursor.execute("SELECT PermissionID, Code, Description FROM Permission ORDER BY sortingcode")
        all_permissions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        return render_template("admin/accessControl.html", 
                             profiles=profiles, 
                             all_permissions=all_permissions,
                             logged_in_user=session.get('username'), userid=session.get('userid'), pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Error loading access control: {e}")
        return render_template('500.html')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/users')
@require_permission('admin.view')
def get_users_admin_access_control():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                u.userID, 
                u.username, 
                u.fullname, 
                ap.Name as AccessProfileName,
                (SELECT COUNT(*) FROM UserPermissionOverride upo WHERE upo.UserID = u.userID) as OverrideCount
            FROM Users u
            LEFT JOIN AccessProfile ap ON u.accessid = ap.AccessID
            ORDER BY u.fullname
        """
        cursor.execute(query)
        
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(users)
    except Exception as e:
        app.logger.error(f"Failed to fetch users for access control: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
@app.route("/api/admin/access_profile/<int:access_id>/details", methods=['GET'])
@require_permission('admin.edit.user')
def get_profile_details(access_id):
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT PermissionID, Effect 
            FROM AccessProfilePermission 
            WHERE AccessID = ?
        """, (access_id,))
        assigned_perms = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify({'success': True, 'permissions': assigned_perms})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/access_profile/save", methods=['POST'])
@require_permission('admin.edit.user')
def save_access_profile():
    data = request.get_json()
    access_id = data.get('accessId') 
    name = data.get('name')
    description = data.get('description')
    permissions = data.get('permissions')

    if not name:
        return jsonify({'success': False, 'message': _("Name is required")}), 400

    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        if access_id:
            cursor.execute("UPDATE AccessProfile SET Name=?, Description=? WHERE AccessID=?", (name, description, access_id))
            cursor.execute("DELETE FROM AccessProfilePermission WHERE AccessID=?", (access_id,))
        else:
            cursor.execute("INSERT INTO AccessProfile (Name, Description) OUTPUT INSERTED.AccessID VALUES (?, ?)", (name, description))
            access_id = cursor.fetchone()[0]

        if permissions:
            params = [(access_id, p['PermissionID'], p['Effect']) for p in permissions]
            cursor.executemany("INSERT INTO AccessProfilePermission (AccessID, PermissionID, Effect) VALUES (?, ?, ?)", params)
        conn.commit()
        session['permissions'] = load_permissions_for_user(session['userid'])
        log_user_action('saveAccessProfile', 'SUCCESS', resource_id=access_id, details={'name': name})
        return jsonify({'success': True, 'message': _("Profile saved successfully")})
    except Exception as e:
        app.logger.error(f"Error saving profile: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/user_overrides/<int:user_id>", methods=['GET'])
@require_permission('admin.edit.user')
def get_user_overrides(user_id):
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT AccessID FROM Users WHERE UserID = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
                return jsonify({'success': False, 'message': "User not found"}), 404
        base_access_id = row[0]
        cursor.execute("SELECT PermissionID, Effect FROM UserPermissionOverride WHERE UserID = ?", (user_id,))
        overrides = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        base_perms = {}
        if base_access_id:
            cursor.execute("SELECT PermissionID, Effect FROM AccessProfilePermission WHERE AccessID = ?", (base_access_id,))
            base_perms = {row.PermissionID: row.Effect for row in cursor.fetchall()}
        return jsonify({
            'success': True, 
            'overrides': overrides, 
            'base_permissions': base_perms
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/user_overrides/save", methods=['POST'])
@require_permission('admin.edit.user')
def save_user_overrides():
    data = request.get_json()
    user_id = data.get('userId')
    overrides = data.get('overrides')

    if not user_id:
        return jsonify({'success': False, 'message': "User ID required"}), 400

    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM UserPermissionOverride WHERE UserID=?", (user_id,))
        
        if overrides:
            params = [(user_id, p['PermissionID'], p['Effect']) for p in overrides]
            cursor.executemany("INSERT INTO UserPermissionOverride (UserID, PermissionID, Effect) VALUES (?, ?, ?)", params)
        
        conn.commit()
        session['permissions'] = load_permissions_for_user(session['userid'])
        log_user_action('saveUserOverrides', 'SUCCESS', target_user_id=user_id)
        return jsonify({'success': True, 'message': _("Overrides updated successfully")})
    except Exception as e:
        app.logger.error(f"Error saving overrides: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# --------------------------- Access Control End ---------------------------- #

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

        conn = engineNexoraDB.raw_connection()
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

        create_notification(userid, _("Password changed successfully"), link=url_for('profile'), icon='fa-unlock')
        log_user_action(action_type='resetUserPassword', status='SUCCESS', resource_id='resetPassword')
        return render_template("reset_password.html", message=_("Password changed"))
    except Exception as e:
        log_user_action(action_type='resetUserPassword', status='FAILURE', resource_id='resetPassword', details={"serverError": str(e)}, IsInternalError=1)
        return
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
            response  = requests.post(uri, headers=headers, data=body, timeout=10)
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

@limiter.limit("5 per hour")
@app.route('/request-password-reset', methods=['GET', 'POST'])
def request_password_reset():
    try:
        request_email = request.form['email']
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE Email = ?", (request_email,))
        rows = cursor.fetchone()

        if rows:
            sendreset = send_reset_email(request_email)
            if sendreset:
                return render_template("forgot_password.html", message=_("A password reset link has been sent to your email"))
            else:
                return render_template('forgot_password.html', error=_("Unexpected error occurred"))
        return render_template('forgot_password.html', error=_("Invalid Email Address"))
    except Exception as e:
        print(e)
        return render_template('forgot_password.html', error=_("Unexpected error occurred"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ---------------------------- forgot password end --------------------------- #

def get_activityinstancesToIgnore():
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT ProcessName, ActivityInstanceName FROM ActivityInstancesToIgnore')
        rows = cursor.fetchall()
        return ', '.join("'"+row.ActivityInstanceName+"'" for row in rows)
    except Exception as e:
        print(e)
    finally:
        if conn: conn.close()
        if cursor: cursor.close()

# ------------------------------ process filter ------------------------------ #
def get_process_filter_and_params(process_name):
    if process_name == '02_Posteingang':
        return "?", ["02_Posteingang"]
    elif process_name == '02_InitialScan':
        return "?", ["02_InitialScan"]
    elif process_name == '03_Invoice_New':
        return "?", ["03_Invoice_New"]
    else:
        return "?, ?, ?", ["02_Posteingang", "03_Invoice_New", "02_InitialScan"]
# ---------------------------- process filter end ---------------------------- #

# --------------------------------- dashboard -------------------------------- #

def get_absolute_dashboard_stats(processName="all"):
    stats = {}
    conn = None

    placeholders, params = get_process_filter_and_params(processName)
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]

    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    activityinstancesToIgnore = get_activityinstancesToIgnore()

    try:
        all_params = params + ['Privera'] + params + ['Privera']
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        query = f"""
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
                    AND a.ActivityInstanceName not in ({activityinstancesToIgnore})
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
            """
        cursor.execute(query, all_params)
        rows = cursor.fetchall()
        stats['ReadyTotal'] = rows[0][0]
        stats['InProgressTotal'] = rows[1][0]
        stats['DoneTotal'] = rows[2][0]
        stats['BacklogTotal'] = rows[3][0]
    except Exception as e:
        print(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return stats

def get_dashbord_preview_documents_stats(processName='all'):
    stats = {}
    conn = None
    placeholders, params = get_process_filter_and_params(processName)
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]

    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    activityinstancesToIgnore = get_activityinstancesToIgnore()

    try:
        all_params = params + ['Privera']
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        query = f"""
            WITH CTE AS (
            SELECT twi.ID WorkItemID, DATEADD(HOUR, 2, twi.ModifiedAt) ModifiedAt,
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
            WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ?
            AND twi.Status <> 2 AND tai.ActivityInstanceName not in ({activityinstancesToIgnore})
        )
        SELECT DISTINCT TOP 20
        WorkItemID
        ,Activity FROM CTE
        WHERE
        CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
        """
        cursor.execute(query, (all_params))
        rows = cursor.fetchall()
    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()

    return jsonify([
            {
                "WorkItemID": row[0],
                "Activity": row[1]
            }
            for row in rows
        ])

@app.route("/dashboard")
@require_permission('dashboard.view')
def dashboard():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get('username', 'Unknown')
        userid = session.get('userid', 'Unknown')
        perms = session.get('permissions', [])

        prefix = "dashboard.filter.process."
        allowed_processes = sorted({
            perm.split('.')[-1]
            for perm in perms
            if perm.startswith(prefix)
        })

        process_name = request.args.get('prcfD', 'all')

        if process_name != 'all' and process_name not in allowed_processes:
            process_name = 'all'

        session['process_name_dashboard'] = process_name
        absolute_stats = get_absolute_dashboard_stats(process_name)

        log_user_action(
            action_type='visitDashboard',
            status='SUCCESS',
            resource_id='dashboard'
        )

        return render_template(
            "dashboard.html",
            logged_in_user=logged_in_user,
            userid=userid,
            ReadyTotal=absolute_stats['ReadyTotal'],
            InProgressTotal=absolute_stats['InProgressTotal'],
            DoneTotal=absolute_stats['DoneTotal'],
            BacklogTotal=absolute_stats['BacklogTotal'],
            process_name=process_name,
            allowed_processes=allowed_processes,  
            pageV=pageVisability()
        )
    except Exception as e:
        log_user_action(
            action_type='visitDashboard',
            status='FAILURE',
            resource_id='dashboard',
            details={"serverError": str(e)},
            IsInternalError=1
        )
        return render_template('500.html')


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

    limit = request.args.get('limit', 10, type=int)

    placeholders, params = get_process_filter_and_params(session.get('process_name_dashboard', 'all'))
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]

    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    all_params = params + ['Privera']
    activityinstancesToIgnore = get_activityinstancesToIgnore()

    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        query = f"""
        WITH CTE AS (
                SELECT
                    twi.ID WorkItemID,
                    DATEADD(HOUR, 2, twi.ModifiedAt) AS ModifiedAt,
                    CASE
                        WHEN twi.Status = 0 THEN 'Ready'
                        WHEN twi.Status = 5 THEN 'Done'
                        ELSE 'In Progress'
                    END AS Status
                FROM t_WorkItems twi
                JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                JOIN t_Processes tp ON tp.ID = tai.ProcessID
                WHERE tp.Name IN ({placeholders}) AND tp.ClientName = ?
                AND twi.Status <> 2 AND tai.ActivityInstanceName not in ({activityinstancesToIgnore})
            )
            SELECT DISTINCT TOP ({limit})
                CTE.WorkItemID,
                CTE.Status,
                CTE.ModifiedAt
            FROM CTE
            ORDER BY CTE.ModifiedAt DESC
        """
        cursor.execute(query,all_params)
        activities = cursor.fetchall()

        return jsonify([
            {
                "state": row.Status,
                "datetime": row.ModifiedAt.strftime('%Y-%m-%d %H:%M:%S'),
                "workitemid": row.WorkItemID
            }
            for row in activities
        ])
    except Exception as e:
        app.logger.error(f"Failed to fetch recent activity: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ------------------------------- dashboard end ------------------------------ #

# ----------------------------- workitem overview ---------------------------- #
@app.route('/api/config/fields')
def api_config_fields():
    if 'username' not in session:
        return jsonify({}), 401

    labels_map = {
        'doctype': _("Document Type"),
        'docbarcode': _("Document Barcode"),
        'ownernr': _("Owner no."),
        'tenancynr': _("Tenancy no."),
        'propertynr': _("Property no."),
        'registered': _("Registered"),
        'branch': _("Branch"),
        'docdate': _("Document Date"),
        'forwarding': _("Forwarding"),
        'department': _("Department"),
        'postcode': _("Postcode"),
        'recipient': _("Recipient"),
        'confidentiality': _("Confidentiality"),
        'crdno': _("Creditor no."),
        'crdname': _("Creditor Name"),
        'bankpk': "Bank PK",
        'grossamount': _("Gross Amount"),
        'netamount': _("Net Amount"),
        'vatamount': _("Vat Amount"),
        'doccurrency': _("Document Currency"),
        'invoicenr': _("Invoice no."),
        'tec': "Tec",
        'esrreference': "ESR Reference",
        'ordernumber': _("Order no."),
        'client': _("Client"),
        'docsource': _("Document Source"),
        'separatorsheet': _("Separator-sheet"),
        'docid': _("Document ID"),
        'archiveboxno': _("Archive-box No."),
        'docno': _("Document No.")
    }

    search_options = {}
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cursor.description if c[0].startswith('col_')]
        
        query = f"SELECT ProcessName, {','.join(cols)} FROM SearchConfig"
        print(query)
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            proc_name = row.ProcessName
            fields = []
            for i, col_name in enumerate(cols):
                if row[i+1]: 
                    field_key = col_name.replace('col_', '')
                    if field_key in labels_map:
                        fields.append({
                            'value': field_key,
                            'label': labels_map[field_key]
                        })
            fields.sort(key=lambda x: x['label'])
            search_options[proc_name] = fields
            
    except Exception as e:
        app.logger.error(f"Error fetching field config: {e}")
    finally:
        if conn:
            conn.close()

    return jsonify({
        'search_options': search_options,
        'labels': labels_map
    })

def prepare_process_selection_sql(prefix,process_name):
    try:
        perms = session.get('permissions', [])
        process_params = []
        client_params = []
        if process_name == 'all':
            unique_processes = set()
            unique_clients = set()
            for perm in perms:
                if perm.startswith(prefix):
                    parts = perm.split('.')
                    client = parts[-2]
                    proc = parts[-1]
                    
                    unique_clients.add(client)
                    unique_processes.add(proc)
            process_params = sorted(list(unique_processes))
            client_params = sorted(list(unique_clients))
        else:
            if has_permission(f'{prefix}{process_name}'):
                parts = process_name.split('.')
                if len(parts) >= 2:
                    client_params = [parts[0]]
                    process_params = [parts[1]]
        process_placeholders = ", ".join(["?"] * len(process_params))
        client_placeholders = ", ".join(["?"] * len(client_params))
        params = process_params + client_params
        print(params)
        print(process_placeholders)
        print(client_placeholders)
        return params, process_placeholders, client_placeholders
    except Exception as e:
        app.logger.error(f"Failed to prepare process selection: {e}")
        raise
    
def _get_workitems_data(args):
    page = args.get('page', 1, type=int)
    search_term = args.get('search', '').strip()
    status = args.get('status', '')
    tag_filter = args.get('tag', '').strip()
    start_date_str = args.get('startDate', '')
    end_date_str = args.get('endDate', '')
    start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
    end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
    priority = args.get('priority', '')
    assigned_user = args.get('assignedUser', '')
    per_page = 40
    offset = (page - 1) * per_page
    activityinstancesToIgnore = get_activityinstancesToIgnore()
    

    process_name = args.get('prcfW', 'all')
    session['process_name_workitemOverview'] = process_name
    prefix = "workitems.filter.process."
    params, process_placeholders, client_placeholders = prepare_process_selection_sql(prefix=prefix,process_name=process_name)

    docfields = args.getlist('docfield')
    docvalues = args.getlist('docvalue')

    where_clauses = [
        f"tp.Name IN ({process_placeholders})",
        f"tp.ClientName IN ({client_placeholders})",
        "twi.Status <> 2",
        f"tai.ActivityInstanceName not in ({activityinstancesToIgnore})"
    ]
    print(where_clauses)
    status_map = {'Ready': 0, 'In Progress': 1, 'Done': 5}
    if status and status in status_map:
        where_clauses.append("twi.Status = ?")
        params.append(status_map[status])
    if tag_filter and has_permission('workitems.filter.tag'):
        where_clauses.append(f"""
            EXISTS (
                SELECT 1
                FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                WHERE wt.workitemid = twi.id AND t.TagName like ?
            )
        """)
        params.append(f"%{tag_filter}%")
    if search_term and has_permission('workitems.filter.workitemid'):
        where_clauses.append("twi.id LIKE ?")
        params.append(f"%{search_term}%")

    if start_date and has_permission('workitems.filter.datetime'):
        where_clauses.append("twi.ModifiedAt >= ?")
        params.append(start_date)
    if end_date and has_permission('workitems.filter.datetime'):
        where_clauses.append("twi.ModifiedAt < ?")
        params.append(end_date)
    if priority and has_permission('workitems.filter.priority'):
        where_clauses.append("wim.Priority = ?")
        params.append(priority)
    if assigned_user and has_permission('workitems.filter.assignedUser'):
        if assigned_user == 'None' or assigned_user == 'Unassigned':
            where_clauses.append("(wim.AssignedUserID IS NULL)")
        else:
            where_clauses.append("wim.AssignedUserID = ?")
            params.append(assigned_user)

    if has_permission('workitems.filter.documentfields'):
        for docfield, docvalue in zip(docfields, docvalues):
            docfield = (docfield or '').lower().strip()
            docvalue = (docvalue or '').strip()
            conn_nex = engineNexoraDB.raw_connection()
            cursor_nex = conn_nex.cursor()

            if not docvalue or not docfield:
                continue

            target_config_col = f'col_{docfield}'

            if target_config_col:
                query = f"SELECT * FROM SearchConfig WHERE {target_config_col} IS NOT NULL"
                sql_params = []
                
                if process_name != 'all':
                    query += " AND ProcessName = ?"
                    sql_params.append(process_name)
                    
                configs = cursor_nex.execute(query, sql_params).fetchall()
                
                generated_checks = []
                
                for config in configs:
                    tbl = config.TableName
                    alias = config.TableAlias
                    join_cond = config.JoinCondition
                    time_filter = config.TimeFilter
                    db_column = getattr(config, target_config_col) 

                    snippet = f"""
                        EXISTS (
                            SELECT 1 
                            FROM [{DB_STATISTICS}].{tbl} {alias} 
                            WHERE {join_cond} 
                            AND {alias}.{db_column} COLLATE DATABASE_DEFAULT LIKE ? 
                            AND {time_filter}
                        )
                    """
                    print(snippet, docvalue)
                    generated_checks.append(snippet)
                    params.append(f"%{docvalue}%")

                if generated_checks:
                    combined_clause = " OR ".join(generated_checks)
                    where_clauses.append(f"({combined_clause})")

            else:
                pass
            conn_nex.close()
            cursor_nex.close()
            
    where_sql = " AND ".join(where_clauses)
    
    workitems_list = []
    total_items = 0
    conn = None
    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()

        count_query = f"""
            SELECT COUNT(twi.ID)
            FROM t_WorkItems twi
            INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
            INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
            LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.workitemid
            WHERE {where_sql}
        """
        cursor.execute(count_query, params)
        total_items = cursor.fetchone()[0] or 0

        data_query = f"""
            WITH WorkitemCTE AS (
                SELECT
                    twi.ModifiedAt, twi.ID AS WorkItemID,
                    CASE
                        WHEN twi.Status = 0 THEN 'Ready' WHEN twi.Status = 5 THEN 'Done' ELSE 'In Progress'
                    END AS Status,
                    CASE
                        WHEN twi.Status = 5 THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'Validation'
                        WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'Import'
                        WHEN tai.ActivityInstanceName LIKE '%Extract%' OR tai.ActivityInstanceName LIKE '%OCR%' THEN 'Extraction'
                        WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' THEN 'Delivery'
                        ELSE 'Extraction'
                    END AS CurrentStage,
                    wim.Priority,
                    (
                        SELECT t.TagID AS id, t.TagName AS name, t.TagColor AS color
                        FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                        JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.WorkItemID = twi.ID
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.WorkItemID
                WHERE {where_sql}
            )
            SELECT 
             ModifiedAt, WorkItemID, Status, CurrentStage, Priority, TagsJSON
            FROM WorkitemCTE WHERE rn = 1
            ORDER BY ModifiedAt DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        data_params = params + [offset, per_page]
        cursor.execute(data_query, data_params)
        for row in cursor.fetchall():
            workitems_list.append({
                'modifiedat': row.ModifiedAt,
                'workitemid': row.WorkItemID,
                'status': row.Status,
                'current_stage': row.CurrentStage,
                'priority': row.Priority or 0,
                'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
            })
    except Exception as e:
        app.logger.error(f"Database error in _get_workitems_data: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    total_pages = math.ceil(total_items / per_page)
    return {
        'workitems': workitems_list,
        'pagination': {
            'currentPage': page,
            'totalPages': total_pages,
            'totalItems': total_items,
            'perPage': per_page
        }
    }

@app.route('/api/docfield_values')
@require_permission('workitems.filter.documentfields')
def api_docfield_values():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    process = request.args.get('process', 'all')
    field = (request.args.get('field', '') or '').lower().strip()
    q = (request.args.get('q', '') or '').strip()
    if not field:
        return jsonify([]) 
    target_col_name = f'col_{field}'
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cur = conn.cursor()

        query = f"SELECT * FROM SearchConfig WHERE {target_col_name} IS NOT NULL"
        db_params = []
        if process != 'all':
            query += " AND ProcessName = ?"
            db_params.append(process)

        configs = cur.execute(query, db_params).fetchall()

        if not configs:
            return jsonify([])

        union_parts = []
        sql_params = []

        for config in configs:
            tbl = config.TableName
            col_name = getattr(config, target_col_name)
            time_filter = config.SuggestionTimeFilter

            part = f"""
                SELECT {col_name} COLLATE DATABASE_DEFAULT AS Val
                FROM [{DB_STATISTICS}].{tbl}
                WHERE {col_name} IS NOT NULL AND {col_name} <> ''
                  AND {time_filter}
            """
            if q:
                part += f" AND {col_name} COLLATE DATABASE_DEFAULT LIKE ?"
                sql_params.append(f"%{q}%")
            
            union_parts.append(part)
        full_union_sql = " UNION ALL ".join(union_parts)
        final_sql = f"""
            SELECT DISTINCT TOP 15 Val 
            FROM (
                {full_union_sql}
            ) t
            ORDER BY Val
        """
        cur.execute(final_sql, sql_params)
        rows = cur.fetchall()
        results = [row.Val for row in rows]
        return jsonify(results)
    except Exception as e:
        app.logger.error(f"/api/docfield_values error: {e}")
        return jsonify({"error": _("Could not fetch values")}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

@app.route("/api/workitems")
@require_permission('workitems.view')
def api_workitems():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    try:
        data = _get_workitems_data(request.args)
        log_user_action('apiVisitWorkitemOverview', status='SUCCESS', resource_id='workitemOverview')
        return jsonify(data)
    except Exception as e:
        log_user_action('apiVisitWorkitemOverview', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
        app.logger.error(f"API error in workitems overview: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

@app.route("/workitems")
@require_permission('workitems.view')
def workitems_overview():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))

        logged_in_user = session.get('username')
        userid = session.get('userid')

        data = _get_workitems_data(request.args)

        workitems_list = data['workitems']
        pagination = data['pagination']

        search_term_perm = has_permission('workitems.filter.workitemid')
        search_term = request.args.get('search', '').strip() if search_term_perm else None

        status_perm = has_permission('workitems.filter.status')
        status = request.args.get('status', '') if status_perm else None

        tag_filter_perm = has_permission('workitems.filter.tag')
        tag_filter = request.args.get('tag', '').strip() if tag_filter_perm else None

        datetime_perm = has_permission('workitems.filter.datetime')
        start_date_str = request.args.get('startDate', '') if datetime_perm else None
        end_date_str = request.args.get('endDate', '') if datetime_perm else None
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else None
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else None

        priority_perm = has_permission('workitems.filter.priority')
        priority = request.args.get('priority', '') if priority_perm else None

        assigned_user_perm = has_permission('workitems.filter.assignedUser')
        assigned_user = request.args.get('assignedUser', '') if assigned_user_perm else None
        
        perms = session.get('permissions', [])
        prefix = "workitems.filter.process."
        allowed_processes = sorted({
            (perm.split('.')[-2] + '.' + perm.split('.')[-1])
            for perm in perms
            if perm.startswith(prefix)
        })

        process_name = request.args.get('prcfW', 'all')
        if process_name != 'all' and process_name not in allowed_processes:
            process_name = 'all'

        docFieldsValues_perm = has_permission('workitems.filter.documentfields')
        docfields = request.args.getlist('docfield') if docFieldsValues_perm else None
        docvalues = request.args.getlist('docvalue') if docFieldsValues_perm else None

        details_view_perm = has_permission('workitems.details.view')
        details_images_perm = has_permission('workitems.details.view.images')
        details_audit_perm = has_permission('workitems.details.view.audit')
        details_fields_perm = has_permission('workitems.details.view.fields')

        details_set_priority_perm = has_permission('workitems.details.set.priority')
        details_add_tag_perm = has_permission('workitems.details.add.tag')
        details_assign_users_perm = has_permission('workitems.details.assign.users')
        details_add_comment_perm = has_permission('workitems.details.add.comment')

        portal_assignedUsers_filter = get_all_portal_users('workitems', 'filter.assignedUser')
        log_user_action('visitWorkitemOverview', status='SUCCESS', resource_id='workitemOverview')
        return render_template("workitems_overview.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            workitems=workitems_list,
            current_page=pagination['currentPage'],
            total_pages=pagination['totalPages'],
            total_items=pagination['totalItems'],
            search=search_term,
            status=status,
            tag=tag_filter,
            startDate=start_date,
            endDate=end_date,
            priority=priority,
            assignedUser=assigned_user,
            portal_assignedUsers_filter=portal_assignedUsers_filter,
            docfield=docfields[0] if docfields else '',
            docvalue=docvalues[0] if docvalues else '',
            pageV=pageVisability(),
            allowed_processes=allowed_processes,
            search_term_perm=search_term_perm,
            status_perm=status_perm,
            tag_filter_perm=tag_filter_perm,
            datetime_perm=datetime_perm,
            priority_perm=priority_perm,
            assigned_user_perm=assigned_user_perm,
            docFieldsValues_perm=docFieldsValues_perm,
            details_view_perm=details_view_perm,
            details_images_perm=details_images_perm,
            details_audit_perm=details_audit_perm,
            details_fields_perm=details_fields_perm,
            details_set_priority_perm=details_set_priority_perm,
            details_add_tag_perm=details_add_tag_perm,
            details_assign_users_perm=details_assign_users_perm,
            details_add_comment_perm=details_add_comment_perm
        )
    except Exception as e:
        log_user_action('visitWorkitemOverview', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')


ALLOWED_MIME_TYPES = {
    'pdf': ['application/pdf'],
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': '[image/jpeg]'
}

def is_file_allowed(filename, file_stream):
    if '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_MIME_TYPES:
        return False
    header = file_stream.read(2048)
    file_stream.seek(0) 
    mime = magic.from_buffer(header, mime=True)
    if mime in ALLOWED_MIME_TYPES[ext]:
        return True
    return False


@app.route('/import_workitems', methods=['POST'])
@require_permission('workitems.import.workitem')
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

    if file and is_file_allowed(file.filename, file.stream):
        filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        upload_folder = os.path.join(app.root_path, 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)

        try:
            file.save(file_path)
            log_user_action('importWorkitems', status='SUCCESS', resource_id='workitemOverview', details={'filename': filename, 'originalFilename': file.filename})
            flash(_("File '{}' successfully imported.").format(filename), 'success')
        except Exception as e:
            app.logger.error(f"Error saving imported file: {e}")
            log_user_action('importWorkitems', status='FAILURE', resource_id='workitemOverview', details={"serverError": str(e)}, IsInternalError=1)
            flash(_("An error occurred while saving the file."), 'error')
    else:
        log_user_action('importWorkitems', status='FAILURE', resource_id='workitemOverview', details={'securityError': 'Invalid file type or spoofed extension', 'filename': file.filename})
        flash(_("Invalid file type. Please upload a valid PDF."), 'error')

    return redirect(url_for('workitems_overview'))

@app.route('/api/workitem/<int:workitemid>')
def get_single_workitem(workitemid):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()

        query = f"""
            WITH WorkitemCTE AS (
                SELECT
                    twi.ID AS WorkItemID,
                    (
                        SELECT
                            t.TagID AS id,
                            t.TagName AS name,
                            t.TagColor AS color
                        FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                        JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.WorkItemID = twi.ID
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY twi.ID ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                WHERE twi.ID = ?
            )
            SELECT WorkItemID, TagsJSON
            FROM WorkitemCTE
            WHERE rn = 1
        """
        cursor.execute(query, workitemid)
        row = cursor.fetchone()

        if not row:
            return jsonify({"error": "Workitem not found"}), 404

        workitem_data = {
            # 'barcode': row.Barcode,
            'workitemid': row.WorkItemID,
            'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
        }
        return jsonify(workitem_data)
    except Exception as e:
        app.logger.error(f"Failed to fetch single workitem {row.WorkItemID}: {e}")
        return jsonify({"error": _("Could not fetch workitem data")}), 500
    finally:
        if cursor:
            cursor.close()
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
        response = requests.post(url=url, headers=headers, data=body, timeout=10)
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
    response = requests.get(url=url, headers=headers, timeout=10)
    str_content = json.dumps(response.json())
    base64_bytes = base64.b64encode(str_content.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')

    return base64_string, response.json()['DocumentID']

cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 300})

@cache.cached(timeout=3600, key_prefix='index_field_mappings')
def get_index_field_mappings():
    mapping = {}
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SourceFieldName, TargetKey FROM IndexFieldMappings")
        for row in cursor.fetchall():
            mapping[row.SourceFieldName] = row.TargetKey
            
    except Exception as e:
        app.logger.error(f"Failed to load IndexFieldMappings: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
    return mapping

def get_extensions_urls_fields(workitemdata, document_id):
    url = f'https://prd-dps.sydoc.ch/api/documentservice/api/v2.1/documentService/thin/Document/{document_id}?WithExtensions=false&WithDocumentStructure=true&WithTables=false&WithDocumentAudits=true&LoadMediaStreams=true'
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "workitemdata": workitemdata
    }
    
    try:
        response = requests.get(url=url, headers=headers, timeout=10)
        response.raise_for_status()
        doc_json = response.json()
    except Exception as e:
        app.logger.error(f"Error fetching document details: {e}")
        return [], [], {}

    urls = []
    extensions = []
    fields = {}
    
    field_mapping = get_index_field_mappings()

    items_to_process = []
    if doc_json.get('DocumentType') == 'Batch' and doc_json.get('ChildDocuments'):
        items_to_process = doc_json['ChildDocuments']
    else:
        items_to_process = [doc_json]

    for item in items_to_process:
        media_list = item.get('Media') or []
        for media in media_list:
            ext = str(media.get('Extension', '')).lower()
            if ext in ('.jpg', '.jpeg', '.png', '.tif'):
                urls.append(media['Url'])
                extensions.append(ext)

        index_fields = item.get('IndexFields') or []
        for field_obj in index_fields:
            source_name = field_obj.get('Name')
            if source_name in field_mapping:
                target_key = field_mapping[source_name]
                field_value = field_obj.get('FieldValue', {}).get('Text')
                if target_key not in fields and field_value is not None:
                    fields[target_key] = field_value
    return extensions, urls, fields

def get_media(url):
    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url=url, headers=headers, timeout=10)
    return response.content


@app.route('/api/get_media_info/<int:workitem_id>')
def api_get_media_info(workitem_id):
    if not has_permission('workitems.details.view'):
         return jsonify({"error": _("Not authorized")}), 403
    try:
        can_view_images = has_permission('workitems.details.view.images')
        can_view_fields = has_permission('workitems.details.view.fields')

        cached_info = cache.get(f"media_info_{workitem_id}")
        if cached_info:
            response_data = cached_info.copy()
            if not can_view_images:
                response_data['media_count'] = 0
            if not can_view_fields:
                response_data['fields'] = {}
            return jsonify(response_data)

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

        filtered_response = response_data.copy()
        if not can_view_images:
             filtered_response['media_count'] = 0
        if not can_view_fields:
             filtered_response['fields'] = {}

        return jsonify(filtered_response)
    except Exception as e:
        print(f"An error occurred in get_media_info: {e}")
        return jsonify({"error": _("Internal Server Error")}), 500

@app.route('/api/get_media_raw/<int:workitem_id>/<int:media_index>')
@require_permission('workitems.details.view.images')
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
            'Cache-Control', 'private, max-age=3600'
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
        response = requests.get(url=activity_instances_url, headers=headers, timeout=10)
        response.raise_for_status()
        activity_instance_config = response.json()
        return activity_instance_config.get('ActivityTypeName', 'Unknown Activity')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching activity instance {activity_instance_id}: {e}")
        return _("Error fetching activity instance")

@app.route('/api/get_audithistory/<int:workitem_id>')
@require_permission('workitems.details.view.audit') 
def get_audithistory(workitem_id):
    try:
        audit_url = f'https://prd-dps.sydoc.ch/api/processservice/api/v2.1/processService/WorkItemAudits?WorkItemID={workitem_id}&VerifyAuditSignatures=true&ExportSignatureVerificationCertificates=true'
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url=audit_url, headers=headers, timeout=10)
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
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        if has_permission('workitems.details.add.comment'):
            if has_permission('admin.view.allusers'):
                cursor.execute("""
                SELECT userID, username, fullname FROM Users
                """)
            else:
                cursor.execute("""
                SELECT userID, username, fullname FROM Users
                WHERE organizationcode IN ('SYDC', ?) AND accessid not in (1,2)
                """, session.get('organizationcode'))
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(users)
    except Exception as e:
        app.logger.error(f"Failed to fetch users for mentions: {e}")
        return jsonify({"error": _("Could not fetch users")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/interactions')
def get_workitem_interactions(workitemid):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        sql_query = """
            SELECT c.CommentText, c.Timestamp, u.username, u.userID
            FROM Workitem_Comments c
            JOIN Users u ON c.UserID = u.userID
        """
        params = [workitemid]

        sql_query += " WHERE c.WorkItemID = ?"

        sql_query += " ORDER BY c.Timestamp ASC"
        cursor.execute(sql_query, params)
        comments_data = cursor.fetchall()

        cursor.execute("""
            SELECT t.TagID, t.TagName, t.TagColor
            FROM Workitem_Tags wt
            JOIN Tags t ON wt.TagID = t.TagID
            WHERE wt.workitemid = ?
        """, (workitemid,))
        tags_data = cursor.fetchall()

        cursor.execute("""SELECT Priority, AssignedUserID FROM Workitem_Metadata
                        WHERE WorkItemID = ?"""
                       , (workitemid,))
        meta_row = cursor.fetchone()

        if meta_row is None and not comments_data and not tags_data:
            return jsonify({
                'priority': 0,
                'assigneduserid': 'None',
                'comments': [],
                'tags': [],
                'message': _("No data found for this workitem.")
            }), 200

        priority = meta_row[0] if (meta_row and meta_row[0] is not None) else 0
        assigneduserid = meta_row[1] if (meta_row and meta_row[1] is not None) else 'None'
        tags = [{'id': trow.TagID, 'name': trow.TagName, 'color': trow.TagColor} for trow in tags_data] if tags_data else []


        comments = []
        if comments_data:
            for crow in comments_data:
                comments.append({
                    'CommentText': crow.CommentText,
                    'Timestamp': crow.Timestamp.isoformat(),
                    'username': crow.username,
                    'userID': crow.userID
                })
        return jsonify({
            'priority': priority,
            'assigneduserid': assigneduserid,
            'comments': comments,
            'tags': tags
        })
    except Exception as e:
        app.logger.error(f"Failed to fetch interactions for workitem {workitemid}: {e}")
        return jsonify({"error": _("Could not fetch interactions")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/comment', methods=['POST'])
def add_workitem_comment(workitemid):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    comment_text = data.get('commentText')
    if not comment_text:
        return jsonify({'success': False, 'message': _("Comment cannot be empty.")}), 400

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO Workitem_Comments (WorkItemID, UserID, CommentText)
            VALUES (?, ?, ?)
        """, (workitemid, session['userid'], comment_text))

        cursor.execute("SELECT SCOPE_IDENTITY()")
        comment_id = cursor.fetchone()[0]

        mentions = re.findall(r'@(\w+)', comment_text)
        if mentions:
            placeholders = ','.join('?' for _ in mentions)
            cursor.execute(f"SELECT userID, username FROM Users WHERE username IN ({placeholders})", mentions)
            mentioned_users = cursor.fetchall()

            for user in mentioned_users:
                cursor.execute("INSERT INTO Comment_Mentions (CommentID, MentionedUserID) VALUES (?, ?)", (comment_id, user.userID))
                notification_link = url_for('workitems_overview', search=workitemid, _external=False)
                create_notification(user.userID, f"{session['username']} mentioned you on workitem {workitemid}", link=notification_link, icon='fa-at')

        conn.commit()
        log_user_action('addWorkitemComment', status='SUCCESS', resource_id=workitemid)
        return jsonify({'success': True, 'message': _("Comment added.")})
    except Exception as e:
        app.logger.error(f"Error adding comment for workitem {workitemid}: {e}")
        log_user_action('addWorkitemComment', status='FAILURE', resource_id=workitemid, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/assign', methods=['POST'])
def assign_workitem(workitemid):
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
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETDATE())) AS source (WorkItemID, AssignedUserID, UserID, UpdateTime)
            ON target.WorkItemID = source.WorkItemID
            WHEN MATCHED THEN
                UPDATE SET AssignedUserID = source.AssignedUserID, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (WorkItemID, AssignedUserID, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.WorkItemID, source.AssignedUserID, source.UserID, source.UpdateTime);
        """, (workitemid, assignedUserID, session['userid']))

        conn.commit()
        log_user_action('assignUserToWorkitem', status='SUCCESS', resource_id=workitemid, details={'assignedUserID': assignedUserID})
        if assignedUserID != None and assignedUserID != session['userid']:
            notification_link = url_for('workitems_overview', search=workitemid, _external=False)
            create_notification(assignedUserID, f"{session['username']} {_('assigned you on workitem')} {workitemid}", link=notification_link, icon='fa-people-carry-box')
        return jsonify({'success': True, 'message': _("Assignment updated.")})
    except Exception as e:
        app.logger.error(f"Error setting assignment for workitem {workitemid}: {e}")
        log_user_action('assignUserToWorkitem', status='FAILURE', resource_id=workitemid, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/priority', methods=['POST'])
def set_workitem_priority(workitemid):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    priority = data.get('priority')
    if priority is None or priority not in [0, 1, 2, 3]:
        return jsonify({'success': False, 'message': _("Invalid priority level.")}), 400

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            MERGE Workitem_Metadata AS target
            USING (VALUES (?, ?, ?, GETDATE())) AS source (WorkItemID, Priority, UserID, UpdateTime)
            ON target.WorkItemID = source.WorkItemID
            WHEN MATCHED THEN
                UPDATE SET Priority = source.Priority, LastUpdatedByUserID = source.UserID, LastUpdatedAt = source.UpdateTime
            WHEN NOT MATCHED THEN
                INSERT (WorkItemID, Priority, LastUpdatedByUserID, LastUpdatedAt)
                VALUES (source.WorkItemID, source.Priority, source.UserID, source.UpdateTime);
        """, (workitemid, priority, session['userid']))

        conn.commit()
        log_user_action('setWorkitemPriority', status='SUCCESS', resource_id=workitemid, details={'priority': priority})
        return jsonify({'success': True, 'message': _("Priority updated.")})
    except Exception as e:
        app.logger.error(f"Error setting priority for workitem {workitemid}: {e}")
        log_user_action('setWorkitemPriority', status='FAILURE', resource_id=workitemid, details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/tags')
def get_all_tags():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
        tags = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(tags)
    except Exception as e:
        app.logger.error(f"Failed to fetch all tags: {e}")
        return jsonify({"error": _("Could not fetch tags")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/tags', methods=['POST'])
def add_tag_to_workitem(workitemid):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    data = request.get_json()
    tag_name = data.get('tagName', '').strip()
    tag_color = data.get('tagColor', '#6B7280')

    if not tag_name:
        return jsonify({'success': False, 'message': _("Tag name cannot be empty.")}), 400

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT TagID FROM Tags WHERE TagName = ?", (tag_name,))
        tag = cursor.fetchone()

        if tag:
            tag_id = tag.TagID
        else:
            cursor.execute("INSERT INTO Tags (TagName, TagColor, CreatedByUserID) OUTPUT INSERTED.TagID VALUES (?, ?, ?)",
                           (tag_name, tag_color, session['userid']))
            tag_id = cursor.fetchone().TagID

        cursor.execute("SELECT 1 FROM Workitem_Tags WHERE WorkItemID = ? AND TagID = ?", (workitemid, tag_id))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': _("Workitem already has this tag.")}), 409

        cursor.execute("INSERT INTO Workitem_Tags (WorkItemID, TagID) VALUES (?, ?)", (workitemid, tag_id))
        conn.commit()

        log_user_action('addWorkitemTag', status='SUCCESS', resource_id=workitemid, details={'tagName': tag_name})
        return jsonify({'success': True, 'message': _("Tag added successfully."), 'tag': {'TagID': tag_id, 'TagName': tag_name, 'TagColor': tag_color}})

    except Exception as e:
        app.logger.error(f"Error adding tag to workitem {workitemid}: {e}")
        log_user_action('addWorkitemTag', status='FAILURE', resource_id=workitemid, details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitem/<int:workitemid>/tags/<int:tag_id>', methods=['DELETE'])
def remove_tag_from_workitem(workitemid, tag_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM Workitem_Tags WHERE WorkItemID = ? AND TagID = ?", (workitemid, tag_id))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': _("Tag association not found.")}), 404

        log_user_action('removeWorkitemTag', status='SUCCESS', resource_id=workitemid, details={'tagId': tag_id})
        return jsonify({'success': True, 'message': _("Tag removed successfully.")})
    except Exception as e:
        app.logger.error(f"Error removing tag {tag_id} from workitem {workitemid}: {e}")
        log_user_action('removeWorkitemTag', status='FAILURE', resource_id=workitemid, details={'serverError': str(e)}, IsInternalError=1)
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ---------------------- workitem collaboration apis end --------------------- #


# -------------------------------- team board --------------------------------- #
@app.route("/team-board")
@require_permission('teamboard.view')
def team_board():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        
        perms = session.get('permissions', [])
        prefix = "teamboard.filter.process."
        allowed_processes = sorted({
            perm.split('.')[-1]
            for perm in perms
            if perm.startswith(prefix)
        })
        process_name = request.args.get('prcfB', 'all')
        if process_name != 'all' and process_name not in allowed_processes:
            process_name = 'all'

        placeholders, params = get_process_filter_and_params(process_name)
        allowed_params = [
            p for p in params
            if has_permission(f'teamboard.filter.process.privera.{p}')
        ]
        placeholders = ", ".join(["?"] * len(allowed_params))
        params = allowed_params
        params.append('Privera')
        
        priority = request.args.get('priority', '')
        activityinstancesToIgnore = get_activityinstancesToIgnore()

        where_clauses = [
            f"tp.Name IN ({placeholders})",
            "tp.ClientName = ?",
            f"tai.ActivityInstanceName not in ({activityinstancesToIgnore})"
        ]

        if priority:
            where_clauses.append("wim.Priority = ?")
            params.append(priority)

        where_sql = " AND ".join(where_clauses)

        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            WITH BoardItems AS (
                SELECT
                    twi.id WorkitemID,
                    twi.ModifiedAt,
                    CASE
                        WHEN twi.Status = 5 THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%C+A%' THEN 'Validation'
                        WHEN tai.ActivityInstanceName LIKE '%Export%' OR tai.ActivityInstanceName LIKE '%Exp%' THEN 'Delivery'
                        WHEN tai.ActivityInstanceName LIKE '%Import%' OR tai.ActivityInstanceName LIKE '%Imp%' THEN 'Import'
                        WHEN tai.ActivityInstanceName LIKE '%Extract%' OR tai.ActivityInstanceName LIKE '%OCR%' THEN 'Extraction'
                        WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' THEN 'Delivery'
                        ELSE 'Extraction'
                    END AS CurrentStage,
                    wim.Priority,
                    wim.AssignedUserID,
                    (
                        SELECT t.TagName AS name, t.TagColor AS color
                        FROM [{DB_NEXORA}].dbo.Workitem_Tags wt
                        JOIN [{DB_NEXORA}].dbo.Tags t ON wt.TagID = t.TagID
                        WHERE wt.workitemid = twi.id
                        FOR JSON PATH
                    ) AS TagsJSON,
                    ROW_NUMBER() OVER(PARTITION BY twi.id ORDER BY twi.ModifiedAt DESC) as rn
                FROM t_WorkItems twi
                INNER JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN t_Processes tp ON tp.ID = tai.ProcessID
                LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.workitemid
                WHERE {where_sql}
            )
            SELECT --Barcode,
            WorkitemID,
            ModifiedAt, CurrentStage, Priority, AssignedUserID, TagsJSON
            FROM BoardItems
            WHERE rn = 1
            ORDER BY Priority DESC, ModifiedAt ASC;
        """
        ,params)
        
        portal_users = get_all_portal_users('teamboard', 'view')
        workitems_by_user = {user['userID']: [] for user in portal_users}
        workitems_by_user['Unassigned'] = []

        for row in cursor.fetchall():
            user_id = row.AssignedUserID if row.AssignedUserID else 'Unassigned'
            if user_id in workitems_by_user:
                workitems_by_user[user_id].append({
                    'workitemid': row.WorkitemID,
                    'modifiedat': row.ModifiedAt,
                    'current_stage': row.CurrentStage,
                    'priority': row.Priority or 0,
                    'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
                })

        log_user_action('visitTeamBoard', status='SUCCESS', resource_id='teamBoard')

        return render_template("team_board.html",
            workitems_by_user=workitems_by_user,
            process_name=process_name,
            priority=priority,
            portal_users=portal_users,
            userid=session.get('userid'),
            pageV=pageVisability(),
            allowed_processes=allowed_processes,
            logged_in_user=session.get('username')
        )
    except Exception as e:
        app.logger.error(f"Error loading team board: {e}")
        log_user_action('visitTeamBoard', status='FAILURE', resource_id='teamBoard', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ------------------------------ process board end ------------------------------- #


# --------------------------- workitem overview end -------------------------- #

def get_all_portal_users(fromRequest, action):
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        if has_permission(f'{fromRequest}.{action}'):
            if has_permission('admin.view.allusers'):
                cursor.execute("""
                SELECT userID, fullname FROM Users
                """)
            else:
                cursor.execute("SELECT userID, fullname FROM Users WHERE organizationCode in (?, 'SYDC') AND accessid not in (1,2) ORDER BY fullname", session.get('organizationcode'))

        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return users
    except Exception as e:
        app.logger.error(f"Failed to fetch all portal users: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ---------------------------------- profile --------------------------------- #
@app.route("/profile")
def profile():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        logged_in_user = session.get('username', 'Unknown')
        userid = session.get('userid', 'Unknown')
        fullname = session.get('fullname', 'Unknown')
        email = session.get('email', 'Unknown')
        log_user_action('visitUserProfile', status='SUCCESS', resource_id='profile')
        return render_template("profile.html", userid=userid, logged_in_user=logged_in_user, fullname=fullname, email=email, pageV=pageVisability())
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

            if not re.search("^((?!\.)[\w\-_.]*[^.])(@\w+)(\.\w+(\.\w+)?[^.\W])$", email) or len(email) >= 50:
                flash(_("Email Adress is not valid"), 'failure_updateProfile')
                return redirect(url_for("profile"))

            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE Users
                SET fullname = ?, email = ?
                WHERE username = ?
            """, (fullname, email, username))

            conn.commit()
            

            session['fullname'] = fullname
            session['email'] = email

            if 'file' in request.files and request.files['file'].filename != '':
                f = request.files['file']
                if not is_file_allowed(f.filename, f.stream):
                    flash(_("Invalid file format. Please upload a valid image."), 'failure_updateProfile')
                    return redirect(url_for("profile"))
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
            })
            create_notification(userid, _("Your profile was updated successfully."), link=url_for('profile'), icon='fa-user-pen')
            flash(_("Profile updated successfully!"), 'success_updateProfile')
            return redirect(url_for("profile"))
    except Exception as e:
        flash(_("Unexpected error"), 'failure_updateProfile')
        log_user_action(action_type='updateUserProfile', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(url_for("profile"))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
                flash(_('New passwords do not match'), 'failure_changePW')
                return redirect(url_for('profile'))
            if not newPassword or not confirmPassword or not currentPassword:
                flash(_("All fields must be filled"), 'failure_changePW')
                return redirect(url_for('profile'))
            if not re.search('^\S{8,200}$', newPassword):
                flash(_("New password has to be atleast 8 characters long, with no whitespaces"), 'failure_changePW')
                return redirect(url_for('profile'))
            conn = engineNexoraDB.raw_connection()
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

                create_notification(userid, _("Password updated successfully!"), link=url_for('profile'), icon='fa-user-shield')
                log_user_action(action_type='changeUserPassword', status='SUCCESS', resource_id='profile')
                flash(_("Password updated successfully!"), 'success_changePW')
                return redirect(url_for('profile'))
            else:
                flash(_("Current password is incorrect"), 'failure_changePW')
                return redirect(url_for('profile'))
    except Exception as e:
        flash(_("Unexpected Error"), 'failure_changePW')
        log_user_action(action_type='changeUserPassword', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(url_for('profile'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/language/<lang>')
def set_language(lang=None):
    try:
        userid = session['userid']
        session['locale'] = lang
        create_notification(userid, _("Language changed successfully!"), link=url_for('profile'), icon='fa-language')
        log_user_action(action_type='changeUserLanguage', status='SUCCESS', resource_id='profile', details={"new_language": lang})
        flash(_("Language changed successfully!"), 'success_setLanguage')
        return redirect(url_for('profile'))
    except Exception as e:
        flash(_("Unexpected Error"), 'failure_setLanguage')
        log_user_action(action_type='changeUserLanguage', status='FAILURE', resource_id='profile', details={"serverError": str(e)}, IsInternalError=1)
        return redirect(url_for('profile'))

@app.context_processor
def inject_current_lang():
    return {'current_lang': str(get_locale())}

@app.context_processor
def utility_processor():
    def get_user_icon_url(user_id):
        if not user_id:
            return url_for('static', filename='images/default-Icon.png')
        
        filename_lower = f"{user_id}-icon.png"
        path_lower = os.path.join(app.root_path, 'static', 'images', filename_lower)
        
        if os.path.exists(path_lower):
            timestamp = int(os.path.getmtime(path_lower))
            return url_for('static', filename=f'images/{filename_lower}', v=timestamp)
            
        filename_upper = f"{user_id}-Icon.png"
        path_upper = os.path.join(app.root_path, 'static', 'images', filename_upper)
        
        if os.path.exists(path_upper):
            timestamp = int(os.path.getmtime(path_upper))
            return url_for('static', filename=f'images/{filename_upper}', v=timestamp)
            
        return url_for('static', filename='images/default-Icon.png')
        
    return dict(get_user_icon_url=get_user_icon_url)
# -------------------------------- profile end ------------------------------- #

# ---------------------------------- jdvance --------------------------------- #
@app.route('/jdvance')
@require_permission('jd.view')
def jdvance():
    return render_template("jd/jdvance.html")
# -------------------------------- jdvance end ------------------------------- #

# ---------------------------------- reports --------------------------------- #

@app.route("/api/reports/processed_over_time")
def report_processed_over_time():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    _, params = get_process_filter_and_params(session['process_name_dashboard'])
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]
    params = allowed_params


    conn = None
    try:
        conn = engineStatisticsDB.raw_connection()
        cursor = conn.cursor()

        rows = []
        for param in params:
            if param == '03_Invoice_New':
                cursor.execute(f"""
                    select CAST(ExportDate AS DATE) d,count(*) c from [{DB_STATISTICS}].dbo.PriveraInvoice
                    where ExportDate >= dateadd(day,-14,getdate()) and GeloeschtAm is null
                    group by CAST(ExportDate AS DATE)
            """)
            elif param == '02_Posteingang':
                cursor.execute(f"""
                    select CONVERT(date, exportdatetime,104) d,count(*) c from [{DB_STATISTICS}].dbo.PriveraPosteingang
                    where CONVERT(date, exportdatetime,104) >= dateadd(day,-14,getdate()) and DokumentGeloescht is null
                    group by CONVERT(date, exportdatetime,104)
            """)
            elif param == '02_InitialScan':
                cursor.execute(f"""
                    select cast(Export as date) d, count(WorkitemID) c from [{DB_STATISTICS}].dbo.PriveraInitialUndNeuzugaenge
                    where Export >= dateadd(day,-14,getdate())
                    group by cast(Export as date)
            """)
            rows += cursor.fetchall()
        rows.sort(key=lambda r: r.d)  
        labels = [row.d for row in rows]
        data = [row.c for row in rows]
        return jsonify({'labels': labels, 'data': data})
    except Exception as e:
        app.logger.error(f"Failed to fetch processed_over_time report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/reports/status_distribution")
def report_status_distribution():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    start_str = request.args.get('startDate')
    end_str   = request.args.get('endDate')
    statuses_q = request.args.get('statuses')
    process_name = session['process_name_dashboard']

    placeholders, params = get_process_filter_and_params(process_name)
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]

    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    all_params = params + ['Privera']

    name_to_code = {'ready':0,'in progress':1,'done':5}
    status_codes = [0,1,5]
    if statuses_q:
        status_codes = [name_to_code[s.strip().lower()] for s in statuses_q.split(',') if s.strip().lower() in name_to_code]

    if not start_str and not end_str and set(status_codes)=={0,1,5}:
        stats = get_absolute_dashboard_stats(process_name)
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
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        activityinstancesToIgnore = get_activityinstancesToIgnore()

        placeholders_status = ','.join(['?']*len(status_codes))
        query = f"""
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
                AND tai.ActivityInstanceName not in ({activityinstancesToIgnore})
            )
            SELECT S, COUNT(*) Cnt FROM Mapped WHERE S <> 'Other' GROUP BY S;
        """
        cursor.execute(query, *(all_params + status_codes + date_params))
        counts = {'Ready':0,'In Progress':0,'Done':0}
        for s,c in cursor.fetchall():
            counts[s] = c

        stats_abs = get_absolute_dashboard_stats(process_name)

        return jsonify({
            'labels': ['Ready','In Progress','Done','Backlog'],
            'data': [counts['Ready'], counts['In Progress'], counts['Done'], stats_abs.get('BacklogTotal',0)]
        })
    except Exception as e:
        app.logger.error(f"Failed to fetch status_distribution report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/reports/kpi_stats")
def report_kpi_stats():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None

    placeholders, params = get_process_filter_and_params(session['process_name_dashboard'])
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]
    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    all_params = params + ['Privera']

    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        processed_today = 0
        processed_week = 0
        for param in params:
            if param == '03_Invoice_New':
                cursor.execute(f"""
                    select count(*) from [{DB_STATISTICS}].dbo.PriveraInvoice
                    where CAST(ExportDate AS DATE) = CAST(GETDATE() AS DATE) and GeloeschtAm is null
                """)
                processed_today += cursor.fetchone()[0]
                cursor.execute(f"""
                        select
                            count(distinct i.wid)
                            from [{DB_STATISTICS}].dbo.PriveraInvoice i
                            WHERE i.ExportDate >= DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()), 0)
                            AND i.ExportDate < DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()) + 1, 0) and GeloeschtAm is null;
                """)
                processed_week += cursor.fetchone()[0]
            elif param == '02_Posteingang':
                cursor.execute(f"""
                    select count(*) from [{DB_STATISTICS}].dbo.PriveraPosteingang
                    where CONVERT(DATE, ExportDatetime,104) = CAST(GETDATE() AS DATE) and DokumentGeloescht is null
                """)
                processed_today += cursor.fetchone()[0]
                cursor.execute(f"""
                        select
                        count(distinct P.WorkItemID)  
                        from [{DB_STATISTICS}].dbo.PriveraPosteingang p
                        WHERE CONVERT(DATE, p.ExportDatetime,104) >= DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()), 0)
                        AND CONVERT(DATE, p.ExportDatetime,104) < DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()) + 1, 0) and DokumentGeloescht is null;
                """)
                processed_week += cursor.fetchone()[0]
            elif param == '02_InitialScan':
                cursor.execute(f"""
                    select count(WorkitemID) from [{DB_STATISTICS}].dbo.PriveraInitialUndNeuzugaenge
                    where cast(export as date) = cast(getdate() as date)
                """)
                processed_today += cursor.fetchone()[0]
                cursor.execute(f"""
                        select count(*)
                        from [{DB_STATISTICS}].dbo.PriveraInitialUndNeuzugaenge
                        WHERE Export >= DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()), 0)
                        AND Export < DATEADD(WEEK, DATEDIFF(WEEK, 0, GETDATE()) + 1, 0);
                    """)
                processed_week += cursor.fetchone()[0]

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
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/reports/stage_breakdown")
def report_stage_breakdown():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401

    start_str = request.args.get('startDate')
    end_str   = request.args.get('endDate')
    statuses_q = request.args.get('statuses')

    placeholders, params = get_process_filter_and_params(session['process_name_dashboard'])
    allowed_params = [
        p for p in params
        if has_permission(f'dashboard.filter.process.privera.{p}')
    ]

    placeholders = ", ".join(["?"] * len(allowed_params))
    params = allowed_params
    all_params = params + ['Privera']

    name_to_code = {'ready':0,'in progress':1,'done':5}
    status_codes = [0,1]
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
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()

        placeholders_status = ','.join(['?']*len(status_codes))
        activityinstancesToIgnore = get_activityinstancesToIgnore()

        query = f"""
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
              AND tai.ActivityInstanceName not in ({activityinstancesToIgnore})
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
        """
        cursor.execute(query, *(all_params + status_codes + date_params))

        rows = cursor.fetchall()
        labels = [row.Activity for row in rows]
        data = [row.ItemCount for row in rows]
        return jsonify({'labels': labels, 'data': data})
    except Exception as e:
        app.logger.error(f"Failed to fetch stage_breakdown report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# -------------------------------- reports end ------------------------------- #

# -------------------------------- bexio ------------------------------------- #

def searchBexioInvoices(clientId, dateFrom, dateTo, search_nr=None, status=None):
    url = "https://api.bexio.com/2.0/kb_invoice/search"
    accessToken = BEXIO_PAT
    if not accessToken:
        app.logger.error("BEXIO_PAT is not set.")
        return []

    headers = {
        'Accept': "application/json",
        'Authorization': f"Bearer {accessToken}",
    }

    payload = [
        {"field": "contact_id", "value": str(clientId), "criteria": "="},
        {"field": "is_valid_from", "value": dateFrom, "criteria": ">="},
        {"field": "is_valid_to", "value": dateTo, "criteria": "<="}
    ]

    if search_nr:
        payload.append({"field": "document_nr", "value": f"%{search_nr}%", "criteria": "LIKE"})

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        invoices = response.json()

        if status:
            status_map = {
                'Paid': [9],
                'Open': [8]
            }
            target_status_ids = status_map.get(status, [])
            if target_status_ids:
                invoices = [inv for inv in invoices if inv.get('kb_item_status_id') in target_status_ids]

        for inv in invoices:
            inv['status_info'] = map_invoice_status(inv.get('kb_item_status_id'))
            try:
                inv['total'] = f"{float(inv['total']):.2f}"
            except (ValueError, TypeError):
                inv['total'] = "0.00"

        return invoices

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Bexio API search failed: {e}")
        log_user_action('searchBexioInvoices', 'FAILURE', resource_id='invoices', details={"serverError": str(e)}, IsInternalError=1)
        return []
    except json.JSONDecodeError:
        app.logger.error(f"Bexio API returned invalid JSON.")
        log_user_action('searchBexioInvoices', 'FAILURE', resource_id='invoices', details={"serverError": "Bexio API returned invalid JSON"}, IsInternalError=1)
        return []

def getBexioInvoicePDF(invoice_id):
    url = f"https://api.bexio.com/2.0/kb_invoice/{invoice_id}/pdf"
    accessToken = BEXIO_PAT
    if not accessToken:
        app.logger.error("BEXIO_PAT is not set.")
        return None, None

    headers = {
        'Accept': "application/json",
        'Authorization': f"Bearer {accessToken}",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        content = data.get('content')
        name = data.get('name')

        if not content or not name:
            app.logger.error(f"Bexio API response for PDF {invoice_id} missing content or name.")
            return None, None

        return base64.b64decode(content), name

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Bexio API PDF fetch failed for {invoice_id}: {e}")
        log_user_action('getBexioInvoicePDF', 'FAILURE', resource_id=invoice_id, details={"serverError": str(e)}, IsInternalError=1)
        return None, None

def map_invoice_status(status_id):
    if status_id == 9:
        return {'text': _('Paid'), 'color': 'green'}
    else:
        return {'text': _('Open'), 'color': 'blue'}

def getBexioClientId():
    clientId = None
    if has_permission('invoices.view.privera'):
        clientId = BEXIO_PRIVERA_CLIENT_ID

    return clientId
# -------------------------------- bexio end --------------------------------- #


# ---------------------------------- invoices ---------------------------------- #
@app.route("/invoices")
@require_permission('invoices.view')
def invoices():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get('username', 'Unknown')
        userid = session.get('userid', 'Unknown')

        search_nr_perm = has_permission('invoices.filter.invoiceid')
        search_nr = request.args.get('search', '') if search_nr_perm else None
        status_perm = has_permission('invoices.filter.status')
        status = request.args.get('status', '') if status_perm else None
        date_perm = has_permission('invoices.filter.date')
        dateFrom = request.args.get('dateFrom',(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')) if date_perm else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        dateTo = request.args.get('dateTo',datetime.now().strftime('%Y-%m-%d')) if date_perm else datetime.now().strftime('%Y-%m-%d')

        log_user_action('visitInvoices', status='SUCCESS', resource_id='invoices')

        return render_template("invoices.html",
                               logged_in_user=logged_in_user,
                               userid=userid,
                               search=search_nr,
                               status=status,
                               dateFrom=dateFrom,
                               dateTo=dateTo
                               ,search_nr_perm=search_nr_perm
                               ,status_perm=status_perm
                               ,date_perm=date_perm
                               ,pageV=pageVisability())
    except Exception as e:
        log_user_action('visitInvoices', status='FAILURE', resource_id='invoices', details={"serverError": str(e)}, IsInternalError=1)
        return render_template('500.html')

@app.route("/api/invoices")
@require_permission('invoices.view')
def api_invoices():
    try:
        if 'username' not in session:
            return jsonify({"error": _("Not authorized")}), 401

        search_nr = request.args.get('search', '') if has_permission('invoices.filter.invoiceid') else None
        status = request.args.get('status', '')  if has_permission('invoices.filter.status') else None
        dateFrom = request.args.get('dateFrom',(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')) if has_permission('invoices.filter.date') else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        dateTo = request.args.get('dateTo',datetime.now().strftime('%Y-%m-%d')) if has_permission('invoices.filter.date') else datetime.now().strftime('%Y-%m-%d')

        bexio_client_id = getBexioClientId()

        if not bexio_client_id:
            app.logger.warn(f"No Bexio Client ID found for user {session.get('username')}")
            return jsonify([])

        invoices_list = searchBexioInvoices(
            clientId=bexio_client_id,
            dateFrom=dateFrom,
            dateTo=dateTo,
            search_nr=search_nr,
            status=status
        )


        log_user_action('apiSearchInvoices', status='SUCCESS', resource_id='invoices', details={
            "filter_search": search_nr,
            "filter_status": status,
            "filter_dateFrom": dateFrom,
            "filter_dateTo": dateTo
        })

        return jsonify(invoices_list)

    except Exception as e:
        log_user_action('apiSearchInvoices', status='FAILURE', resource_id='invoices', details={"serverError": str(e)}, IsInternalError=1)
        return jsonify({"error": "Failed to fetch invoices"}), 500

@app.route("/invoice/<int:invoice_id>/pdf")
@require_permission('invoices.download')
def download_invoice_pdf(invoice_id):
    if 'username' not in session:
        return redirect(url_for("login"))

    try:
        pdf_content, pdf_name = getBexioInvoicePDF(invoice_id)

        if pdf_content and pdf_name:
            log_user_action('downloadBexioPDF', status='SUCCESS', resource_id=invoice_id)
            return Response(
                pdf_content,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment;filename={pdf_name}'}
            )
        else:
            log_user_action('downloadBexioPDF', status='FAILURE', resource_id=invoice_id, details={"error": "PDF content not found in Bexio."})
            flash(_("Could not download PDF. File not found or API error."), 'error')
            return redirect(url_for('invoices'))

    except Exception as e:
        log_user_action('downloadBexioPDF', status='FAILURE', resource_id=invoice_id, details={"serverError": str(e)}, IsInternalError=1)
        app.logger.error(f"Failed to download invoice PDF {invoice_id}: {e}")
        flash(_("An unexpected error occurred while downloading the PDF."), 'error')
        return redirect(url_for('invoices'))
# -------------------------------- invoices end -------------------------------- #




# ------------------------------- ONLY FOR PROD -------------------------------- #
# app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/nexora')
# ----------------------------- ONLY FOR PROD end ------------------------------ #


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
