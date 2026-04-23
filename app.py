import math
import uuid
from fileinput import filename
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, Response, make_response, send_file
from flask_babel import Babel, gettext, ngettext, _
from flask_session import Session
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
import urllib, csv

# -------------------------------- app config -------------------------------- #
app = Flask(__name__)
load_dotenv()
load_dotenv(dotenv_path=f'{os.environ.get("ENVIRONMENT")}.env')
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
    app=app
)

app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET_KEY")
# app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
# app.config['SESSION_COOKIE_SECURE'] = True 
# app.config['SESSION_COOKIE_HTTPONLY'] = True
# app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# app.config['SESSION_TYPE'] = 'filesystem'  
# app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'session') 
# app.config['SESSION_PERMANENT'] = True
# app.config['SESSION_USE_SIGNER'] = True    

# Session(app)

csrf = CSRFProtect(app)
# csp = {
#     'default-src': '\'self\'',
#     'base-uri': '\'self\'',         
#     'object-src': '\'none\'',       
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
DB_SERVER_PRD_MOBSCAN = os.environ.get("DB_SERVER_PRD_MOBSCAN")
DB_NEXORA = os.environ.get("DB_NEXORA")
DB_STATISTICS = os.environ.get("DB_STATISTICS")
DB_STATISTICS_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].{DB_STATISTICS}"
DB_OCTO_RUNTIME = os.environ.get("DB_OCTO_RUNTIME")
DB_OCTO_RUNTIME_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].{DB_OCTO_RUNTIME}"
RUNTIME_TBL_MOBSCAN = f"[{DB_SERVER_PRD_MOBSCAN}].[{DB_OCTO_RUNTIME}].[dbo]."
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
OCTO_CLIENT_SECRET = os.environ.get("OCTO_CLIENT_SECRET")
OCTO_CLIENT_ID = os.environ.get("OCTO_CLIENT_ID")
OCTO_CLIENT_SECRET_MOBSCN = os.environ.get("OCTO_CLIENT_SECRET_MOBSCN")
OCTO_CLIENT_ID_MOBSCN = os.environ.get("OCTO_CLIENT_ID_MOBSCN")
OCTO_GRANT_TYPE = os.environ.get("OCTO_GRANT_TYPE")
BEXIO_PAT = os.environ.get("BEXIO_PAT")
OCTO_DOMAIN = os.environ.get("OCTO_DOMAIN")
OCTO_DOMAIN_MOBSCN = os.environ.get("OCTO_DOMAIN_MOBSCN")

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
def getDBUrl(d, s=DB_SERVER_PRD):
    params = urllib.parse.quote_plus(
            f'DRIVER={{SQL Server}};'
            f'SERVER={s},1433;'
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
engineStatisticsDBMobscan = create_engine(
    getDBUrl(DB_STATISTICS, DB_SERVER_PRD_MOBSCAN),
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800
)
DB_GENERALI = os.environ.get("DB_GENERALI", "Generali")
engineGeneraliDB = create_engine(
    getDBUrl(DB_GENERALI),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800
)

# ------------------------------ database connection end --------------------- #

# ---------------------------------- logging --------------------------------- #
def get_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0]
    else:
        return request.remote_addr or 'Unknown'
    
@app.before_request
def start_timer():
    request.start_time = time.time()

@app.before_request
def reload_user_permissions():
    if request.path.startswith('/static'):
        return
    if 'userid' in session:
        try:
            session['permissions'] = load_permissions_for_user(str(session['userid']))
        except Exception as e:
            app.logger.error(f"reload_user_permissions error: {e}")

@app.before_request
def load_user_locale():
    if 'userid' in session and 'locale' not in session:
        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT locale FROM Users WHERE userid = ?", [session['userid']])
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row[0] in ['de', 'en', 'fr', 'it']:
                session['locale'] = row[0]
        except Exception as e:
            app.logger.error(f"load_user_locale error: {e}")

@app.after_request
def log_every_request(response):
    if request.path.startswith('/static'):
        return response
    duration = time.time() - request.start_time if hasattr(request, 'start_time') else 0

    try:
        LOGS_FOLDER = os.path.join(app.root_path, 'logs')
        os.makedirs(LOGS_FOLDER, exist_ok=True)

        LOGS_HOUR_FOLDER = os.path.join(LOGS_FOLDER, datetime.now().strftime("%Y%m%d%H"))
        os.makedirs(LOGS_HOUR_FOLDER, exist_ok=True)

        with open(f'{LOGS_HOUR_FOLDER}/nexora_logs.csv', 'a', newline='') as csvfile:
            fieldnames = ['SessionID', 'RequestIpAddress', 'UserID', 'Username', 'HttpRequestMethod', 'Path', 'HttpResponseCode', 'Args', 'durationSeconds']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if csvfile.tell() == 0:
                writer.writeheader()
            writer.writerow({
                'SessionID': session.get('uuid'),
                'RequestIpAddress': get_ip(),
                'UserID': session.get('userid'),
                'Username': session.get('username'),
                'HttpRequestMethod': request.method,
                'Path': request.path,
                'HttpResponseCode': response.status_code,
                'Args': request.args.to_dict(),
                'durationSeconds': round(duration, 4),
            })
    except Exception as e:
        app.logger.error(f"Logging failed: {e}")
    return response

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

def require_any_permission(*codes):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'username' not in session:
                return redirect(url_for('login'))
            if not any(has_permission(c) for c in codes):
                raise PermissionDenied()
            return f(*args, **kwargs)
        return wrapper
    return decorator

def _check_generali_record_org(cursor, table, user_id_col, record_id):
    """Raises PermissionDenied if record belongs to a user outside the current user's org."""
    cursor.execute(f"SELECT {user_id_col} FROM {table} WHERE ID = ?", [record_id])
    rec = cursor.fetchone()
    if not rec:
        return  # record not found — UPDATE/DELETE will affect 0 rows
    record_uid = rec[0]
    if record_uid == session.get('userid'):
        return  # own record always allowed
    nx_conn = engineNexoraDB.raw_connection()
    nx_cur = nx_conn.cursor()
    nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [record_uid])
    org_row = nx_cur.fetchone()
    nx_cur.close()
    nx_conn.close()
    if not org_row or org_row[0] != session.get('organizationcode'):
        raise PermissionDenied()

def startpage_redirect_to(pV):
    permToFunction = {
        'dashboardPagePerm': 'dashboard',
        'workitemsPagePerm': 'workitems_overview',
        'invoicesPagePerm': 'invoices',
        'generaliPagePerm': 'generali_evaluation',
        'generaliDocumentsPerm': 'generali_documents',
        'generaliReportingPerm': 'generali_reporting',
        'generaliAdditionalServicesPerm': 'generali_additionalServices',
        'generaliBaseServicesPerm': 'generali_baseServices',
        'generaliProjectManagementPerm': 'generali_projectManagement',
        'generaliPDQMPerm': 'generali_pdqm',
        'chatPagePerm': 'chat_page',
        'adminPagePerm': 'admin_dashboard'
    }
    for pTF in permToFunction:
        if pV[pTF]: return permToFunction[pTF]
    return 'login'

def pageVisability():
    adminPagePerm = has_permission('admin.view')
    dashboardPagePerm = has_permission('dashboard.view')
    workitemsPagePerm = has_permission('workitems.view')
    invoicesPagePerm = has_permission('invoices.view')
    chatPagePerm = has_permission('chat.view')
    generaliPagePerm = has_permission('generali.dashboard.view')
    generaliDocumentsPerm = has_permission('generali.documentlist.view')
    generaliReportingPerm = has_permission('generali.reporting.view')
    generaliAdditionalServicesPerm = has_permission('generali.additionalservices.view')
    generaliBaseServicesPerm = has_permission('generali.baseservices.view')
    generaliProjectManagementPerm = has_permission('generali.projectmanagement.view')
    generaliPDQMPerm = has_permission('generali.pdqm.view')
    return {'adminPagePerm': adminPagePerm, 'dashboardPagePerm': dashboardPagePerm,
            'workitemsPagePerm':workitemsPagePerm,
            'invoicesPagePerm': invoicesPagePerm, 'chatPagePerm': chatPagePerm,
            'generaliPagePerm': generaliPagePerm,
            'generaliDocumentsPerm': generaliDocumentsPerm,
            'generaliReportingPerm': generaliReportingPerm,
            'generaliAdditionalServicesPerm': generaliAdditionalServicesPerm,
            'generaliBaseServicesPerm': generaliBaseServicesPerm,
            'generaliProjectManagementPerm': generaliProjectManagementPerm,
            'generaliPDQMPerm': generaliPDQMPerm}

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

                cursor.execute("SELECT username, fullname, email, organizationcode, locale FROM Users WHERE userid = ?", (user_id,))
                row = cursor.fetchone()

                if not row:
                    return redirect(url_for('login'))

                username, fullname, email, org_code, user_locale = row
                session.pop('temp_2fa_secret', None)

                session.clear()
                session['userid'] = user_id
                session['username'] = username
                session['fullname'] = fullname
                session['email'] = email
                session['organizationcode'] = org_code
                session['uuid'] = uuid.uuid4()
                session['permissions'] = load_permissions_for_user(str(user_id))
                if user_locale in ['de', 'en', 'fr', 'it']:
                    session['locale'] = user_locale
                pV = pageVisability()
                return redirect(url_for(startpage_redirect_to(pV)))
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
        cursor.execute("SELECT TwoFASecret, username, fullname, email, organizationcode, locale FROM Users WHERE userid = ?", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return redirect(url_for('login'))

        secret, username, fullname, email, org_code, user_locale = row

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
            if user_locale in ['de', 'en', 'fr', 'it']:
                session['locale'] = user_locale
            pV = pageVisability()
            return redirect(url_for(startpage_redirect_to(pV)))
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

        if not stored_2FA:
            session['pre_2fa_userid'] = pre_auth_userid
            session['pre_2fa_username'] = stored_username 
            return redirect(url_for('init_2FA'))
        else:
            return redirect(url_for('login'))
    except Exception as e:
        return

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        # DEV ONLY!!!
        if UID_REQUEST == '123' and PWD_REQUEST == '123':
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT username, fullname, email, organizationcode, locale FROM Users WHERE userid = 1019")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            username, fullname, email, org_code, locale = row

            session.clear() 
            session['userid'] = "1019"
            session['username'] = username
            session['fullname'] = fullname
            session['email'] = email
            session['organizationcode'] = org_code
            session['uuid'] = uuid.uuid4()
            session['locale'] = locale
            session['permissions'] = load_permissions_for_user("1019")
            pV = pageVisability()
            return redirect(url_for(startpage_redirect_to(pV)))
        if UID_REQUEST == '321' and PWD_REQUEST == '321':
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT userid, username, fullname, email, organizationcode, locale FROM Users WHERE username = 'demo.user'")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            userid, username, fullname, email, org_code, locale = row

            session.clear() 
            session['userid'] = userid
            session['username'] = username
            session['fullname'] = fullname
            session['email'] = email
            session['organizationcode'] = org_code
            session['uuid'] = uuid.uuid4()
            session['locale'] = locale
            session['permissions'] = load_permissions_for_user(userid)
            pV = pageVisability()
            return redirect(url_for(startpage_redirect_to(pV)))
        if UID_REQUEST == '456' and PWD_REQUEST == '456':
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT userid, username, fullname, email, organizationcode, locale FROM Users WHERE username = 'demo.user2'")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            userid, username, fullname, email, org_code, locale = row

            session.clear() 
            session['userid'] = userid
            session['username'] = username
            session['fullname'] = fullname
            session['email'] = email
            session['organizationcode'] = org_code
            session['uuid'] = uuid.uuid4()
            session['locale'] = locale
            session['permissions'] = load_permissions_for_user(userid)
            pV = pageVisability()
            return redirect(url_for(startpage_redirect_to(pV)))
        if not UID_REQUEST or not PWD_REQUEST:
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
           
            return render_template('index.html', error=_("Invalid credentials"))

        except Exception as e:
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

    user_count = 0
    org_count = 0
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Users")
        row = cursor.fetchone()
        if row: user_count = row[0]
        cursor.execute("SELECT COUNT(*) FROM organizations")
        row = cursor.fetchone()
        if row: org_count = row[0]
    except Exception as e:
        app.logger.error(f"Failed to load admin overview counts: {e}")
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

    return render_template("admin/adminOverview.html",
                         user_count=user_count,
                         org_count=org_count,
                         logged_in_user=session.get('username'),
                         userid=session.get('userid'),
                         pageV=pageVisability())

# @app.route("/admin/mobscn_processmanagement")
# @require_permission('admin.view.mobscn.processmanagement')
# def admin_mobscn_processmanagement():
#     try:
#         conn = engineOctoDB.raw_connection()
#         cursor = conn.cursor()
#         cursor.execute("""
#             select ClientName, Name from [VM-SQLS-MOBSCAN].RuntimeDatabase.dbo.t_Processes where name <> 'System'
#         """)
#         rows = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
#         return render_template("admin/mobscn_processmanagement.html", rows=rows, logged_in_user=session.get('username'),userid=session.get('userid'), pageV=pageVisability())
#     except Exception as e:
#         app.logger.error(f"Failed to fetch mobscn_processmanagement: {e}")
#         return render_template('500.html')
#     finally:
#             if cursor: cursor.close()
#             if conn: conn.close()


@app.route("/admin/organizations")
@require_permission('admin.view.organizations')
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

        return jsonify({'success': True, 'message': _("Organization created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({'success': False, 'message': _("Organization already exists.")}), 409
    except Exception as e:
        app.logger.error(f"Error adding organization: {e}")
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
        
        return jsonify({'success': True, 'message': _("Organization updated successfully.")})
    except Exception as e:
        app.logger.error(f"Error editing Organization {currentUserId}: {e}")
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
            return jsonify({'success': False, 'message': _("Organization not found.")}), 404

        
        return jsonify({'success': True, 'message': _("Organization deleted successfully.")})
    except Exception as e:
        app.logger.error(f"Error deleting Organization {organizationcode}: {e}")
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/organizations/list")
@require_permission('admin.view.organizations')
def api_admin_organizations_list():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT organizationcode, organization FROM organizations ORDER BY organization")
        orgs = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(orgs)
    except Exception as e:
        app.logger.error(f"Failed to fetch organizations list: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/admin/logs")
@require_permission('admin.view.system.logs')
def admin_logs_view():
    return render_template("admin/logs.html", logged_in_user=session.get('username'),userid=session.get('userid'), pageV=pageVisability())

@app.route("/api/admin/logs/search")
@require_permission('admin.view.system.logs')
def api_admin_logs_search():
    username = request.args.get('username', '').strip()
    method = request.args.get('method', '').strip()
    path = request.args.get('path', '').strip()
    
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
    
    if method:
        query_parts.append("HttpRequestMethod = ?")
        params.append(method)
    
    if path:
        query_parts.append("Path LIKE ?")
        params.append(f"%{path}%")

    if status == 'SUCCESS':
        query_parts.append("HttpResponseCode BETWEEN 200 AND 299")
    elif status == 'FAILURE':
        query_parts.append("HttpResponseCode >= 400")

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
        
        cursor.execute(f"SELECT COUNT(*) FROM Logs WHERE {where_clause}", params)
        total_count = cursor.fetchone()[0]

        sql = f"""
            SELECT LogID, Timestamp, Username, HttpRequestMethod, Path, 
                   HttpResponseCode, Args, RequestIpAddress, durationSeconds
            FROM Logs 
            WHERE {where_clause}
            ORDER BY Timestamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        cursor.execute(sql, params + [offset, per_page])
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'LogID': row.LogID,
                'Timestamp': row.Timestamp,
                'Username': row.Username,
                'HttpRequestMethod': row.HttpRequestMethod,
                'Path': row.Path,
                'HttpResponseCode': row.HttpResponseCode,
                'Args': row.Args,
                'RequestIpAddress': row.RequestIpAddress,
                'durationSeconds': row.durationSeconds
            })

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
@require_permission('admin.view.active.sessions')
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
        return jsonify({'success': True, 'message': _("User created successfully.")})
    except pyodbc.IntegrityError:
        return jsonify({'success': False, 'message': _("Username or email already exists.")}), 409
    except Exception as e:
        app.logger.error(f"Error adding user: {e}")
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
        if not has_permission(f'admin.assign.user.accessprofile.{str(accessprofile).lower()}'):
            app.logger.error(f"User does not have Permission: admin.assign.user.accessprofile.{str(accessprofile).lower()} for {user_id}")
            return jsonify({'success': False, 'message': _("Permission Denied for this action.")}), 403
        
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

        return jsonify({'success': True, 'message': _("User updated successfully.")})
    except Exception as e:
        app.logger.error(f"Error editing user {user_id}: {e}")
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

        cursor.execute("delete from Chat_Messages where senderid = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from Chat_Participants where UserID = ?", (user_id,))
        cursor.commit()

        cursor.execute("delete from users where userid = ?", (user_id,))
        cursor.commit()

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': _("User not found.")}), 404

        return jsonify({'success': True, 'message': _("User deleted successfully.")})
    except Exception as e:
        app.logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({'success': False, 'message': _("An error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/users/list")
@require_permission('admin.view.users')
def api_admin_users_list():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT userID, username, fullname, email, ap.name accessprofile, o.organization organization
            FROM Users u
            JOIN accessprofile ap ON ap.accessid = u.accessid
            JOIN organizations o ON o.organizationcode = u.organizationcode
            ORDER BY username
        """)
        users = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(users)
    except Exception as e:
        app.logger.error(f"Failed to fetch users list: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/recent_logs")
@require_permission('admin.view.active.sessions')
def admin_recent_logs():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 20 Timestamp, Username, HttpRequestMethod, Path, HttpResponseCode
            FROM Logs
            ORDER BY Timestamp DESC
        """)
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'Timestamp': row.Timestamp,
                'Username': row.Username,
                'ActionType': f"{row.HttpRequestMethod} {row.Path}", 
                'ActionStatus': 'SUCCESS' if 200 <= row.HttpResponseCode < 300 else 'FAILURE'
            })
        return jsonify(logs)
    except Exception as e:
        app.logger.error(f"Failed to fetch recent logs: {e}")
        return jsonify({"error": _("Could not fetch logs")}), 500
    finally:
        if conn: conn.close()

@app.route("/api/admin/active_sessions")
@require_permission('admin.view.active.sessions')
def admin_active_sessions():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
				Username,
				Userid,
                RequestIpAddress as IPAddress,
                MAX(Timestamp) as LastActivity
            FROM Logs
            WHERE Timestamp >= DATEADD(minute, -30, getdate())
            GROUP BY SessionID, Username, RequestIpAddress, Userid
            ORDER BY LastActivity DESC
        """)
        sessions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(sessions)
    except Exception as e:
        app.logger.error(f"Failed to fetch active sessions: {e}")
        return jsonify({"error": _("Could not fetch sessions")}), 500
    finally:
        if conn: conn.close()
# ----------------------------- Access Control ------------------------------ #
@app.route("/admin/access_control")
@require_permission('admin.view.accessprofiles.useroverrides')
def admin_access_control():
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ap.AccessID, ap.Name, ap.Description, COUNT(u.userID) AS UserCount
            FROM AccessProfile ap
            LEFT JOIN Users u ON u.accessID = ap.AccessID
            GROUP BY ap.AccessID, ap.Name, ap.Description
            ORDER BY ap.Name
        """)
        profiles = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        cursor.execute("SELECT PermissionID, Code, Description FROM Permission ORDER BY sortingcode")
        all_permissions = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]

        organizations = []
        assignable_profiles = []
        if has_permission('admin.view.users'):
            cursor.execute("SELECT organizationcode, organization FROM Organizations ORDER BY organization")
            organizations = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
            cursor.execute("SELECT ap.name profile, ap.accessid accessid FROM AccessProfile ap ORDER BY ap.name")
            all_ap = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
            for ap in all_ap:
                if has_permission(f'admin.assign.user.accessprofile.{str(ap["profile"]).lower()}'):
                    assignable_profiles.append(ap)

        return render_template("admin/accessControl.html",
                             profiles=profiles,
                             all_permissions=all_permissions,
                             organizations=organizations,
                             assignable_profiles=assignable_profiles,
                             can_edit_accessprofile=has_permission('admin.edit.accessprofile'),
                             can_view_users=has_permission('admin.view.users'),
                             can_create_user=has_permission('admin.create.user'),
                             can_edit_user=has_permission('admin.edit.user'),
                             can_delete_user=has_permission('admin.delete.user'),
                             logged_in_user=session.get('username'), userid=session.get('userid'), pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Error loading access control: {e}")
        return render_template('500.html')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/admin/users')
@require_permission('admin.view.accessprofiles.useroverrides')
def get_users_admin_access_control():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT
                u.userID, u.username, u.fullname, u.email,
                ap.Name AS AccessProfileName, ap.AccessID AS AccessProfileID,
                o.organization,
                (SELECT COUNT(*) FROM UserPermissionOverride upo WHERE upo.UserID = u.userID) AS OverrideCount
            FROM Users u
            LEFT JOIN AccessProfile ap ON u.accessid = ap.AccessID
            LEFT JOIN Organizations o ON u.organizationcode = o.organizationcode
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
@require_permission('admin.view.accessprofiles.useroverrides')
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
@require_permission('admin.edit.accessprofile')
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
@require_permission('admin.view.accessprofiles.useroverrides')
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
@require_permission('admin.edit.user.override')
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
        return jsonify({'success': True, 'message': _("Overrides updated successfully")})
    except Exception as e:
        app.logger.error(f"Error saving overrides: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/admin/permissions/list")
@require_permission('admin.view.accessprofiles.useroverrides')
def api_admin_permissions_list():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.PermissionID, p.Code, p.Description, p.SortingCode,
                (SELECT COUNT(*) FROM AccessProfilePermission a WHERE a.PermissionID = p.PermissionID) AS ProfileCount,
                (SELECT COUNT(*) FROM UserPermissionOverride o WHERE o.PermissionID = p.PermissionID) AS OverrideCount
            FROM Permission p
            ORDER BY p.SortingCode, p.Code
        """)
        perms = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify(perms)
    except Exception as e:
        app.logger.error(f"Error listing permissions: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/permissions/<int:perm_id>/users")
@require_permission('admin.view.accessprofiles.useroverrides')
def api_admin_permission_users(perm_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Code FROM Permission WHERE PermissionID = ?", (perm_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': _("Permission not found")}), 404
        perm_code = row[0]
        cursor.execute("""
            SELECT
                u.userID, u.username, u.fullname,
                ap.Name AS AccessProfileName,
                CAST(dbo.fnUserHasPermission(u.userID, ?) AS INT) AS HasPermission,
                upo.Effect AS OverrideEffect,
                app.Effect AS ProfileEffect
            FROM Users u
            LEFT JOIN AccessProfile ap ON ap.AccessID = u.accessID
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = u.userID AND upo.PermissionID = ?
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = ?
            ORDER BY u.fullname
        """, (perm_code, perm_id, perm_id))
        users = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        app.logger.error(f"Error fetching users for permission {perm_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/users/<int:user_id>/all_permissions")
@require_permission('admin.view.accessprofiles.useroverrides')
def api_admin_user_all_permissions(user_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.PermissionID, p.Code, p.Description, p.SortingCode,
                CAST(dbo.fnUserHasPermission(?, p.Code) AS INT) AS IsEffective,
                upo.Effect AS OverrideEffect,
                app.Effect AS ProfileEffect
            FROM Permission p
            LEFT JOIN Users u ON u.userID = ?
            LEFT JOIN UserPermissionOverride upo ON upo.UserID = ? AND upo.PermissionID = p.PermissionID
            LEFT JOIN AccessProfilePermission app ON app.AccessID = u.accessID AND app.PermissionID = p.PermissionID
            ORDER BY p.SortingCode, p.Code
        """, (user_id, user_id, user_id))
        perms = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        return jsonify({'success': True, 'permissions': perms})
    except Exception as e:
        app.logger.error(f"Error fetching all permissions for user {user_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/permissions/add", methods=['POST'])
@require_permission('admin.edit.accessprofile')
def api_admin_permission_add():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get('code') or '').strip()
    description = (data.get('description') or '').strip()
    sorting_code = (data.get('sortingCode') or '').strip() or None
    if not code or not description:
        return jsonify({'success': False, 'message': _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Permission (Code, Description, SortingCode) OUTPUT INSERTED.PermissionID VALUES (?, ?, ?)",
            (code, description, sorting_code)
        )
        new_id = cursor.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'message': _("Permission created successfully"), 'permissionId': new_id})
    except Exception as e:
        app.logger.error(f"Error creating permission: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/permissions/edit/<int:perm_id>", methods=['POST'])
@require_permission('admin.edit.accessprofile')
def api_admin_permission_edit(perm_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    data = request.get_json()
    code = (data.get('code') or '').strip()
    description = (data.get('description') or '').strip()
    sorting_code = (data.get('sortingCode') or '').strip() or None
    if not code or not description:
        return jsonify({'success': False, 'message': _("Code and description are required")}), 400
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Permission SET Code=?, Description=?, SortingCode=? WHERE PermissionID=?",
            (code, description, sorting_code, perm_id)
        )
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': _("Permission not found")}), 404
        conn.commit()
        return jsonify({'success': True, 'message': _("Permission updated successfully")})
    except Exception as e:
        app.logger.error(f"Error updating permission {perm_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/admin/permissions/delete/<int:perm_id>", methods=['DELETE'])
@require_permission('admin.edit.accessprofile')
def api_admin_permission_delete(perm_id):
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM AccessProfilePermission WHERE PermissionID=?", (perm_id,))
        profile_refs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM UserPermissionOverride WHERE PermissionID=?", (perm_id,))
        override_refs = cursor.fetchone()[0]
        if profile_refs > 0 or override_refs > 0:
            return jsonify({
                'success': False,
                'message': _("Cannot delete: used in %(p)d profile(s) and %(o)d override(s). Remove all assignments first.") % {'p': profile_refs, 'o': override_refs}
            }), 400
        cursor.execute("DELETE FROM Permission WHERE PermissionID=?", (perm_id,))
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'message': _("Permission not found")}), 404
        conn.commit()
        return jsonify({'success': True, 'message': _("Permission deleted successfully")})
    except Exception as e:
        app.logger.error(f"Error deleting permission {perm_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --------------------------- Access Control End ---------------------------- #

# --------------------------------- admin end -------------------------------- #

# ---------------------------------- logout ---------------------------------- #
@app.route("/logout")
def logout():
    try:
        session.pop('username', None)
        session.pop('uuid', None)
        session.pop('userid', None)
        return redirect(url_for("index"))
    except Exception as e:
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

        return render_template("reset_password.html", message=_("Password changed"))
    except Exception as e:
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
        return params, process_placeholders, client_placeholders
    except Exception as e:
        app.logger.error(f"Failed to prepare process selection: {e}")
        raise

def get_activityinstancesToIgnore():
    cached = cache.get('activity_instances_ignore')
    if cached is not None:
        return cached
    conn = None
    cursor = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT ProcessName, ActivityInstanceName FROM ActivityInstancesToIgnore')
        rows = cursor.fetchall()
        result = ', '.join("'"+row.ActivityInstanceName+"'" for row in rows)
        cache.set('activity_instances_ignore', result, timeout=3600)
        return result
    except Exception as e:
        print(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

cache = Cache(app, config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 300})


def get_mobscan_clients():
    cache_key = 'mobscan_client_list'
    clients = cache.get(cache_key)
    if clients is not None:
        return clients

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT processName FROM mobscnClients")
        clients = [row[0] for row in cursor.fetchall()]
        cache.set(cache_key, clients, timeout=3600) 
        return clients
    except Exception as e:
        app.logger.error(f"Failed to fetch Mobscan clients: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def split_processes_by_server(process_list):
    mobscan_set = set(get_mobscan_clients())
    regular = [p for p in process_list if p not in mobscan_set]
    mobscan = [p for p in process_list if p in mobscan_set]
    return regular, mobscan

def get_params_from_process_list(process_list):
    proc_params = sorted({p.split('.')[-1] for p in process_list if '.' in p})
    cli_params  = sorted({p.split('.')[0]  for p in process_list if '.' in p})
    return (
        proc_params + cli_params,
        ", ".join(["?"] * len(proc_params)),
        ", ".join(["?"] * len(cli_params))
    )

def build_stat_query(proc):
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        query = 'SELECT TableName, ExportColumn, additionalCondition FROM Statconfig WHERE ProcessName = ?'
        cursor.execute(query, proc)
        return cursor.fetchone()
    except Exception as e:
        print(e)
    finally:
        if conn: conn.close()
        if cursor: cursor.close()
# --------------------------------- dashboard -------------------------------- #

def make_cache_key(*args, **kwargs):
    return f"{request.path}_{session.get('userid')}_{session.get('process_name_dashboard', 'all')}"





@app.route("/api/dashboard/processed_over_time")
@cache.cached(timeout=300, key_prefix=make_cache_key)
def dashboard_processed_over_time():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401
    
    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted({
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    })
    process_name = session.get('process_name_dashboard', 'all')
    
    target_processes = allowed_processes if process_name == 'all' else [process_name]
    
    if not target_processes:
        return jsonify({'labels': [], 'data': []})

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(target_processes))
        config_query = f"""
            SELECT ProcessName, TableName, ExportColumn, additionalCondition 
            FROM Statconfig 
            WHERE ProcessName IN ({placeholders})
        """
        cursor.execute(config_query, target_processes)
        configs = cursor.fetchall()
        cursor.close()
        conn.close()

        if not configs:
            return jsonify({'labels': [], 'data': []})

        mobscan_set = set(get_mobscan_clients())
        regular_configs = [r for r in configs if r.ProcessName not in mobscan_set]
        mobscan_configs  = [r for r in configs if r.ProcessName in mobscan_set]

        def build_pot_sub_queries(cfg_rows):
            sub_qs = []
            for row in cfg_rows:
                convert = 'convert' in str(row.ExportColumn).lower()
                date_col = f"CAST({row.ExportColumn} AS DATE)" if not convert else row.ExportColumn
                condition = f" {row.additionalCondition}" if row.additionalCondition else ""
                sub_qs.append(f"""
                    SELECT {date_col} as d, COUNT(*) as c
                    FROM [{DB_STATISTICS}].{row.TableName}
                    WHERE {row.ExportColumn} >= DATEADD(day, -14, GETDATE()) {condition}
                    GROUP BY {date_col}
                """)
            return sub_qs

        counts = {} 

        for engine, cfg_group in [
            (engineStatisticsDB, regular_configs),
            (engineStatisticsDBMobscan, mobscan_configs),
        ]:
            sub_queries = build_pot_sub_queries(cfg_group)
            if not sub_queries:
                continue
            full_query = f"""
                SELECT d, SUM(c) as total_count
                FROM ({' UNION ALL '.join(sub_queries)}) as combined_data
                GROUP BY d
                ORDER BY d
            """
            conn = engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute(full_query)
            for row in cursor.fetchall():
                counts[row.d] = counts.get(row.d, 0) + row.total_count
            cursor.close()
            conn.close()
            conn = None

        sorted_dates = sorted(counts.keys())
        return jsonify({'labels': sorted_dates, 'data': [counts[d] for d in sorted_dates]})

    except Exception as e:
        app.logger.error(f"Failed to fetch processed_over_time report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route("/api/dashboard/kpi_stats")
@cache.cached(timeout=60, key_prefix=lambda: f"kpi_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}")
def dashboard_kpi_stats():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get('permissions', [])
    allowed_processes = sorted({
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    })
    process_name = session.get('process_name_dashboard', 'all')
    
    target_processes = allowed_processes if process_name == 'all' else [process_name]

    if not target_processes:
         return jsonify({'processed_today': 0, 'processed_week': 0, 'current_backlog': 0, 'imported_today': 0})

    processed_today = 0
    imported_today = 0
    current_backlog = 0

    conn_nex = None
    conn_stat = None
    conn_octo = None
    
    try:
        conn_nex = engineNexoraDB.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ','.join(['?'] * len(target_processes))
        
        cursor_nex.execute(f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition FROM Statconfig WHERE ProcessName IN ({placeholders})", target_processes)
        configs = cursor_nex.fetchall()

        if configs:
            mobscan_set = set(get_mobscan_clients())
            regular_cfgs = [r for r in configs if r.ProcessName not in mobscan_set]
            mobscan_cfgs  = [r for r in configs if r.ProcessName in mobscan_set]

            def build_kpi_sub_queries(cfg_rows):
                sub_qs = []
                for row in cfg_rows:
                    colExport = row.ExportColumn
                    colImport = row.ImportColumn
                    condition = f" {row.additionalCondition}" if row.additionalCondition else ""
                    sub_qs.append(f"""
                        SELECT
                            SUM(CASE WHEN CAST({colExport} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExport,
                            SUM(CASE WHEN CAST({colImport} AS DATE) = CAST(GETDATE() AS DATE) THEN 1 ELSE 0 END) as TodayCountExportImport
                        FROM [{DB_STATISTICS}].{row.TableName}
                        WHERE CAST({colImport} as date) = cast(GETDATE() as date)
                        {condition}
                    """)
                return sub_qs

            for engine, cfg_group in [
                (engineStatisticsDB, regular_cfgs),
                (engineStatisticsDBMobscan, mobscan_cfgs),
            ]:
                sub_queries = build_kpi_sub_queries(cfg_group)
                if not sub_queries:
                    continue
                full_stat_query = f"""
                    SELECT SUM(TodayCountExport), SUM(TodayCountExportImport)
                    FROM ({' UNION ALL '.join(sub_queries)}) as combined
                """
                conn_stat = engine.raw_connection()
                cursor_stat = conn_stat.cursor()
                cursor_stat.execute(full_stat_query)
                row = cursor_stat.fetchone()
                if row:
                    processed_today += row[0] or 0
                    imported_today  += row[1] or 0
                conn_stat = None

        regular_procs, mobscan_procs = split_processes_by_server(target_processes)

        conn_octo = engineOctoDB.raw_connection()
        cursor_octo = conn_octo.cursor()

        for tbl_prefix, procs in [
            ("", regular_procs),
            (RUNTIME_TBL_MOBSCAN, mobscan_procs),
        ]:
            if not procs:
                continue
            p_params, p_ph, c_ph = get_params_from_process_list(procs)
            cursor_octo.execute(f"""
                SELECT COUNT(*) FROM {tbl_prefix}t_WorkItems w
                LEFT JOIN {tbl_prefix}t_ActivityInstances a on a.id = w.ActivityInstanceID
                LEFT JOIN {tbl_prefix}t_Processes p on p.id = a.ProcessID
                LEFT JOIN {tbl_prefix}t_ActivityTypes act on act.id = a.ActivityTypeID
                WHERE p.Name IN ({p_ph}) AND p.ClientName IN ({c_ph}) AND act.Name = 'C+A';
            """, p_params)
            current_backlog += cursor_octo.fetchone()[0]

        return jsonify({
            'processed_today': processed_today,
            'imported_today': imported_today,
            'current_backlog': current_backlog
        })

    except Exception as e:
        app.logger.error(f"Failed to fetch kpi_stats report: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex: cursor_nex.close()
        if cursor_stat: cursor_stat.close()
        if cursor_octo: cursor_octo.close()
        if conn_nex: conn_nex.close()
        if conn_stat: conn_stat.close()
        if conn_octo: conn_octo.close()

@app.route("/api/dashboard/hourly_stats")
@cache.cached(timeout=120, key_prefix=lambda: f"hourly_stats_{session.get('userid')}_{session.get('process_name_dashboard','all')}")
def dashboard_hourly_stats():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get('permissions', [])
    allowed_processes = sorted({
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    })
    process_name = session.get('process_name_dashboard', 'all')
    target_processes = allowed_processes if process_name == 'all' else [process_name]

    if not target_processes:
        return jsonify({'labels': [f"{h:02d}:00" for h in range(24)], 'data': [0] * 24})

    conn_nex = None
    conn_stat = None
    cursor_nex = None
    cursor_stat = None
    try:
        conn_nex = engineNexoraDB.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ','.join(['?'] * len(target_processes))
        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, additionalCondition FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes
        )
        configs = cursor_nex.fetchall()

        if not configs:
            return jsonify({'labels': [f"{h:02d}:00" for h in range(24)], 'data': [0] * 24})

        mobscan_set = set(get_mobscan_clients())
        regular_cfgs = [r for r in configs if r.ProcessName not in mobscan_set]
        mobscan_cfgs  = [r for r in configs if r.ProcessName in mobscan_set]

        def build_hourly_sub_queries(cfg_rows):
            sub_qs = []
            for row in cfg_rows:
                condition = f" {row.additionalCondition}" if row.additionalCondition else ""
                sub_qs.append(f"""
                    SELECT DATEPART(hour, {row.ExportColumn}) as h, COUNT(*) as c
                    FROM [{DB_STATISTICS}].{row.TableName}
                    WHERE CAST({row.ExportColumn} AS DATE) = CAST(GETDATE() AS DATE) {condition}
                    GROUP BY DATEPART(hour, {row.ExportColumn})
                """)
            return sub_qs

        hourly = {}

        for engine, cfg_group in [
            (engineStatisticsDB, regular_cfgs),
            (engineStatisticsDBMobscan, mobscan_cfgs),
        ]:
            sub_queries = build_hourly_sub_queries(cfg_group)
            if not sub_queries:
                continue
            full_query = f"""
                SELECT h, SUM(c) as total
                FROM ({' UNION ALL '.join(sub_queries)}) as combined
                GROUP BY h
                ORDER BY h
            """
            conn_stat = engine.raw_connection()
            cursor_stat = conn_stat.cursor()
            cursor_stat.execute(full_query)
            for row in cursor_stat.fetchall():
                hourly[row.h] = hourly.get(row.h, 0) + row.total

        return jsonify({
            'labels': [f"{h:02d}:00" for h in range(24)],
            'data': [hourly.get(h, 0) for h in range(24)]
        })

    except Exception as e:
        app.logger.error(f"Failed to fetch hourly_stats: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex: cursor_nex.close()
        if cursor_stat: cursor_stat.close()
        if conn_nex: conn_nex.close()
        if conn_stat: conn_stat.close()


@app.route("/api/dashboard/avg_processing_time")
@cache.cached(timeout=300, key_prefix=lambda: f"avg_proc_time_{session.get('userid')}_{session.get('process_name_dashboard','all')}")
def dashboard_avg_processing_time():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    prefix = "dashboard.filter.process."
    perms = session.get('permissions', [])
    allowed_processes = sorted({
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    })
    process_name = session.get('process_name_dashboard', 'all')
    target_processes = allowed_processes if process_name == 'all' else [process_name]

    if not target_processes:
        return jsonify({'avg_minutes': None, 'avg_display': '—'})

    conn_nex = None
    conn_stat = None
    cursor_nex = None
    cursor_stat = None
    try:
        conn_nex = engineNexoraDB.raw_connection()
        cursor_nex = conn_nex.cursor()
        placeholders = ','.join(['?'] * len(target_processes))
        cursor_nex.execute(
            f"SELECT ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition FROM Statconfig WHERE ProcessName IN ({placeholders})",
            target_processes
        )
        configs = cursor_nex.fetchall()

        mobscan_set = set(get_mobscan_clients())
        regular_cfgs = [r for r in configs if r.ProcessName not in mobscan_set]
        mobscan_cfgs  = [r for r in configs if r.ProcessName in mobscan_set]

        def build_avg_sub_queries(cfg_rows):
            sub_qs = []
            for row in cfg_rows:
                if not row.ImportColumn:
                    continue
                condition = f" {row.additionalCondition}" if row.additionalCondition else ""
                sub_qs.append(f"""
                    SELECT AVG(CAST(DATEDIFF(second, {row.ImportColumn}, {row.ExportColumn}) AS FLOAT)) as avg_sec
                    FROM [{DB_STATISTICS}].{row.TableName}
                    WHERE CAST({row.ExportColumn} AS DATE) = CAST(GETDATE() AS DATE)
                    AND {row.ImportColumn} IS NOT NULL
                    AND {row.ExportColumn} > {row.ImportColumn}
                    {condition}
                """)
            return sub_qs

        avg_values = []

        for engine, cfg_group in [
            (engineStatisticsDB, regular_cfgs),
            (engineStatisticsDBMobscan, mobscan_cfgs),
        ]:
            sub_queries = build_avg_sub_queries(cfg_group)
            if not sub_queries:
                continue
            full_query = f"""
                SELECT AVG(avg_sec) as overall_avg
                FROM ({' UNION ALL '.join(sub_queries)}) as combined
                WHERE avg_sec IS NOT NULL
            """
            conn_stat = engine.raw_connection()
            cursor_stat = conn_stat.cursor()
            cursor_stat.execute(full_query)
            row = cursor_stat.fetchone()
            if row and row[0] is not None:
                avg_values.append(row[0])

        if not avg_values:
            return jsonify({'avg_minutes': None, 'avg_display': '—'})

        avg_sec = sum(avg_values) / len(avg_values)

        avg_minutes = avg_sec / 60
        if avg_minutes < 1:
            display = f"{int(avg_sec)}s"
        elif avg_minutes < 60:
            display = f"{avg_minutes:.0f}min"
        else:
            display = f"{avg_minutes / 60:.1f}h"

        return jsonify({'avg_minutes': round(avg_minutes, 1), 'avg_display': display})

    except Exception as e:
        app.logger.error(f"Failed to fetch avg_processing_time: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor_nex: cursor_nex.close()
        if cursor_stat: cursor_stat.close()
        if conn_nex: conn_nex.close()
        if conn_stat: conn_stat.close()


@app.route("/dashboard")
@require_permission('dashboard.view')
def dashboard():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))

        logged_in_user = session.get('username', 'Unknown')
        userid = session.get('userid', 'Unknown')
        perms = session.get('permissions', [])
        fullname = session.get('fullname')

        prefix = "dashboard.filter.process."
        allowed_processes = sorted({
            (perm.split('.')[-2] + '.' + perm.split('.')[-1])
            for perm in perms
            if perm.startswith(prefix)
        })

        process_name = request.args.get('prcfD', 'all')
        if process_name != 'all' and process_name not in allowed_processes:
            process_name = 'all'

        session['process_name_dashboard'] = process_name

        return render_template(
            "dashboard.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
            allowed_processes=allowed_processes,
            pageV=pageVisability(),
            fullname=fullname
        )
    except Exception as e:
        return render_template('500.html')

@app.route("/api/dashboard/set_filter", methods=["POST"])
@require_permission('dashboard.view')
def dashboard_set_filter():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    perms = session.get('permissions', [])
    prefix = "dashboard.filter.process."
    allowed_processes = sorted({
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    })
    process_name = request.json.get('process_name', 'all')
    if process_name != 'all' and process_name not in allowed_processes:
        process_name = 'all'
    session['process_name_dashboard'] = process_name
    return jsonify({"ok": True, "process_name": process_name})
# ------------------------------- dashboard end ------------------------------ #

# ----------------------------- workitem overview ---------------------------- #
@app.route('/api/config/fields')
def api_config_fields():
    if 'username' not in session:
        return jsonify({}), 401

    perms = session.get('permissions', [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    }

    current_lang = str(get_locale())
    _cache_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)
    lang_column_map = {
        'de': 'GermanLabel',
        'fr': 'FrenchLabel',
        'it': 'ItalianLabel',
        'en': 'EnglishLabel'
    }
    target_column = lang_column_map.get(current_lang, 'EnglishLabel')

    search_options = {}
    db_labels_map = {}
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels")
            for row in cursor.fetchall():
                translated_label = getattr(row, target_column) or row.EnglishLabel
                db_labels_map[row.FieldKey] = translated_label
        except Exception:
            pass 
        
        cursor.execute("SELECT TOP 0 * FROM SearchConfig")
        cols = [c[0] for c in cursor.description if c[0].startswith('col_')]
        
        query = f"SELECT ProcessName, {','.join(cols)} FROM SearchConfig"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            proc_name = row.ProcessName

            if proc_name not in allowed_processes:
                continue

            fields = []
            for i, col_name in enumerate(cols):
                if row[i+1]:
                    field_key = col_name.replace('col_', '')
                    nice_label = db_labels_map.get(field_key, field_key.replace('_', ' ').title())

                    fields.append({
                        'value': field_key,
                        'label': nice_label
                    })
            fields.sort(key=lambda x: x['label'])
            search_options[proc_name] = fields
            
    except Exception as e:
        app.logger.error(f"Error fetching field config: {e}")
    finally:
        if conn:
            conn.close()

    result = {'search_options': search_options, 'labels': db_labels_map}
    cache.set(_cache_key, result, timeout=3600)
    return jsonify(result)

@cache.cached(timeout=3600, key_prefix='search_config_columns')
def get_valid_search_columns():
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 0 * FROM SearchConfig")
        valid_cols = [c[0].lower() for c in cursor.description if c[0].lower().startswith('col_')]
        return valid_cols
    except Exception as e:
        app.logger.error(f"Error fetching search config columns: {e}")
        return []
    finally:
        if conn:
            conn.close()

def _get_workitems_data(args, export_all=False):
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
    if export_all:
        per_page = 5000
        offset = 0
    else:
        per_page = int(args.get('perPage', 40))
        if per_page not in (40, 100, 200, 500, 1000):
            per_page = 40
        offset = (page - 1) * per_page
    activityinstancesToIgnore = get_activityinstancesToIgnore()

    process_name = args.get('prcfW', 'all')
    session['process_name_workitemOverview'] = process_name
    
    prefix = "workitems.filter.process."
    perms = session.get('permissions', [])
    
    allowed_processes_set = set()
    for perm in perms:
        if perm.startswith(prefix):
            parts = perm.split('.')
            if len(parts) >= 2:
                allowed_processes_set.add(f"{parts[-2]}.{parts[-1]}")

    target_processes = []
    if process_name == 'all':
        target_processes = list(allowed_processes_set)
    else:
        if process_name in allowed_processes_set:
            target_processes = [process_name]

    params, process_placeholders, client_placeholders = prepare_process_selection_sql(prefix=prefix, process_name=process_name)

    docfields = args.getlist('docfield')
    docvalues = args.getlist('docvalue')

    where_clauses = [
        f"tp.Name IN ({process_placeholders})",
        f"tp.ClientName IN ({client_placeholders})",
        "twi.Status <> 2",
        f"tai.ActivityInstanceName not in ({activityinstancesToIgnore})"
    ]
    
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
        where_clauses.append("ISNULL(wim.Priority, 0) = ?")
        params.append(priority)
    if assigned_user and has_permission('workitems.filter.assignedUser'):
        if assigned_user == 'None' or assigned_user == 'Unassigned':
            where_clauses.append("(wim.AssignedUserID IS NULL)")
        else:
            where_clauses.append("wim.AssignedUserID = ?")
            params.append(assigned_user)

    regular_extra_clauses = []
    regular_extra_params = []
    mobscan_extra_clauses = []
    mobscan_extra_params = []
    _docfield_temp_tables = []  # [(temp_name, [ids])] for large ID sets

    if has_permission('workitems.filter.documentfields') and target_processes:
        valid_db_columns = get_valid_search_columns()
        mobscan_set_docfield = set(get_mobscan_clients())

        conn_nex = None
        try:
            conn_nex = engineNexoraDB.raw_connection()
            cursor_nex = conn_nex.cursor()

            for docfield, docvalue in zip(docfields, docvalues):
                docfield = (docfield or '').lower().strip()
                docvalue = (docvalue or '').strip()

                if not docvalue or not docfield:
                    continue

                target_config_col = f'col_{docfield}'
                if target_config_col not in valid_db_columns:
                    continue

                placeholders = ','.join(['?'] * len(target_processes))
                query = f"""
                    SELECT ProcessName, TableName, TableAlias, JoinCondition, TimeFilter, {target_config_col}
                    FROM SearchConfig
                    WHERE {target_config_col} IS NOT NULL
                    AND ProcessName IN ({placeholders})
                """
                configs = cursor_nex.execute(query, target_processes).fetchall()

                reg_cfgs = [c for c in configs if c.ProcessName not in mobscan_set_docfield]
                mob_cfgs = [c for c in configs if c.ProcessName in mobscan_set_docfield]

                for stat_engine, cfgs, extra_clauses, extra_params in [
                    (engineStatisticsDB,        reg_cfgs, regular_extra_clauses, regular_extra_params),
                    (engineStatisticsDBMobscan, mob_cfgs, mobscan_extra_clauses, mobscan_extra_params),
                ]:
                    if not cfgs:
                        continue

                    id_parts = []
                    id_params = []
                    for config in cfgs:
                        tbl       = config.TableName
                        alias     = config.TableAlias
                        db_column = getattr(config, target_config_col)
                        time_filter = config.TimeFilter
                        safe_col  = f"CAST({alias}.{db_column} AS NVARCHAR(MAX))"

                        id_col = None
                        for part in re.split(r'\s*=\s*', (config.JoinCondition or '').strip()):
                            if re.match(rf'^{re.escape(alias)}\.\w+$', part.strip(), re.IGNORECASE):
                                id_col = part.strip()
                                break

                        if not id_col:
                            app.logger.warning(f"Could not extract ID col from JoinCondition: {config.JoinCondition}")
                            continue

                        id_parts.append(f"""
                            SELECT DISTINCT {id_col} AS id
                            FROM {tbl} {alias}
                            WHERE {safe_col} COLLATE DATABASE_DEFAULT LIKE ?
                            AND {time_filter}
                        """)
                        id_params.append(f"%{docvalue}%")

                    if not id_parts:
                        continue

                    stat_conn = None
                    try:
                        stat_conn = stat_engine.raw_connection()
                        stat_cur  = stat_conn.cursor()
                        union_sql = " UNION ALL ".join(id_parts)
                        stat_cur.execute(f"SELECT DISTINCT id FROM ({union_sql}) t", id_params)
                        matching_ids = [row[0] for row in stat_cur.fetchall()]
                    except Exception as e:
                        app.logger.error(f"Error pre-fetching docfield IDs: {e}")
                        matching_ids = None
                    finally:
                        if stat_conn:
                            stat_conn.close()

                    if matching_ids is None:
                        continue  # skip this filter on error; don't restrict results
                    if not matching_ids:
                        extra_clauses.append("1=0")
                    elif len(matching_ids) > 500:
                        # Avoid SQL Server's 2100-param limit by using a temp table
                        temp_name = f"#docf{len(_docfield_temp_tables)}"
                        _docfield_temp_tables.append((temp_name, matching_ids))
                        extra_clauses.append(f"twi.ID IN (SELECT id FROM {temp_name})")
                    else:
                        ph = ','.join(['?'] * len(matching_ids))
                        extra_clauses.append(f"twi.ID IN ({ph})")
                        extra_params.extend(matching_ids)

        except Exception as e:
            app.logger.error(f"Error in docfield pre-fetch block: {e}")
        finally:
            if cursor_nex: cursor_nex.close()
            if conn_nex: conn_nex.close()
            
    # Split params into process/client part and common (filter) part so we can
    # re-apply the same common filters for each server group independently.
    n_pc_params = process_placeholders.count('?') + client_placeholders.count('?')
    common_params = list(params[n_pc_params:])
    common_where_clauses_part = where_clauses[2:]  # clauses after tp.Name / tp.ClientName

    regular_procs, mobscan_procs = split_processes_by_server(target_processes)

    workitems_list = []
    total_items = 0
    conn = None
    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()

        # Create temp tables for large docfield ID sets (avoids 2100-param limit)
        for temp_name, ids in _docfield_temp_tables:
            cursor.execute(f"CREATE TABLE {temp_name} (id NVARCHAR(255))")
            for i in range(0, len(ids), 1000):
                batch = ids[i:i + 1000]
                cursor.execute(
                    f"INSERT INTO {temp_name}(id) VALUES {','.join(['(?)'] * len(batch))}",
                    batch
                )

        # --- count pass ---
        for tbl_prefix, procs, extra_cls, extra_pms in [
            ("",                 regular_procs, regular_extra_clauses, regular_extra_params),
            (RUNTIME_TBL_MOBSCAN, mobscan_procs, mobscan_extra_clauses, mobscan_extra_params),
        ]:
            if not procs:
                continue
            grp_pc, grp_proc_ph, grp_cli_ph = get_params_from_process_list(procs)
            grp_where = " AND ".join(
                [f"tp.Name IN ({grp_proc_ph})", f"tp.ClientName IN ({grp_cli_ph})"]
                + common_where_clauses_part
                + extra_cls
            )
            grp_params = grp_pc + common_params + extra_pms
            cursor.execute(f"""
                SELECT COUNT(twi.ID)
                FROM {tbl_prefix}t_WorkItems twi
                INNER JOIN {tbl_prefix}t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                INNER JOIN {tbl_prefix}t_Processes tp ON tp.ID = tai.ProcessID
                LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.workitemid
                WHERE {grp_where}
            """, grp_params)
            total_items += cursor.fetchone()[0] or 0

        # --- data pass ---
        for tbl_prefix, procs, extra_cls, extra_pms in [
            ("",                 regular_procs, regular_extra_clauses, regular_extra_params),
            (RUNTIME_TBL_MOBSCAN, mobscan_procs, mobscan_extra_clauses, mobscan_extra_params),
        ]:
            if not procs:
                continue
            grp_pc, grp_proc_ph, grp_cli_ph = get_params_from_process_list(procs)
            grp_where = " AND ".join(
                [f"tp.Name IN ({grp_proc_ph})", f"tp.ClientName IN ({grp_cli_ph})"]
                + common_where_clauses_part
                + extra_cls
            )
            grp_params = grp_pc + common_params + extra_pms
            cursor.execute(f"""
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
                            WHEN tai.ActivityInstanceName LIKE '%Pause%' or tai.ActivityInstanceName like '%Deletion%' or tai.ActivityInstanceName like '%Lieferung%' THEN 'Delivery'
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
                    FROM {tbl_prefix}t_WorkItems twi
                    INNER JOIN {tbl_prefix}t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                    INNER JOIN {tbl_prefix}t_Processes tp ON tp.ID = tai.ProcessID
                    LEFT JOIN [{DB_NEXORA}].dbo.Workitem_Metadata wim ON twi.id = wim.WorkItemID
                    WHERE {grp_where}
                )
                SELECT ModifiedAt, WorkItemID, Status, CurrentStage, Priority, TagsJSON
                FROM WorkitemCTE WHERE rn = 1
                ORDER BY ModifiedAt DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, grp_params + [offset, per_page])
            for row in cursor.fetchall():
                workitems_list.append({
                    'modifiedat': row.ModifiedAt,
                    'workitemid': row.WorkItemID,
                    'status': row.Status,
                    'current_stage': row.CurrentStage,
                    'priority': row.Priority or 0,
                    'tags': json.loads(row.TagsJSON) if row.TagsJSON else []
                })

        # Merge results from both servers, re-sort and trim to one page
        workitems_list.sort(key=lambda x: x['modifiedat'], reverse=True)
        workitems_list = workitems_list[:per_page]

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

        mobscan_set = set(get_mobscan_clients())
        regular_cfgs = [c for c in configs if c.ProcessName not in mobscan_set]
        mobscan_cfgs  = [c for c in configs if c.ProcessName in mobscan_set]

        cache_key = f'docfield_vals_{process}_{field}'
        all_vals = cache.get(cache_key)

        if all_vals is None:
            def build_union(cfg_rows):
                parts = []
                for config in cfg_rows:
                    tbl = config.TableName
                    col_name = getattr(config, target_col_name)
                    time_filter = config.SuggestionTimeFilter
                    safe_col = f"CAST({col_name} AS NVARCHAR(MAX))"
                    parts.append(f"""
                        SELECT {safe_col} COLLATE DATABASE_DEFAULT AS Val
                        FROM [{DB_STATISTICS}].{tbl}
                        WHERE {col_name} IS NOT NULL
                          AND {safe_col} <> ''
                          AND {time_filter}
                    """)
                return parts

            raw_vals = []
            stat_conn = None
            try:
                for engine, cfg_group in [
                    (engineStatisticsDB, regular_cfgs),
                    (engineStatisticsDBMobscan, mobscan_cfgs),
                ]:
                    parts = build_union(cfg_group)
                    if not parts:
                        continue
                    full_union_sql = " UNION ALL ".join(parts)
                    final_sql = f"""
                        SELECT DISTINCT TOP 500 Val
                        FROM ({full_union_sql}) t
                        ORDER BY Val
                    """
                    stat_conn = engine.raw_connection()
                    stat_cur = stat_conn.cursor()
                    stat_cur.execute(final_sql)
                    raw_vals.extend(row.Val for row in stat_cur.fetchall())
                    stat_cur.close()
                    stat_conn.close()
                    stat_conn = None
            finally:
                if stat_conn:
                    stat_conn.close()

            all_vals = sorted(set(raw_vals))
            cache.set(cache_key, all_vals, timeout=600)

        q_lower = q.lower()
        results = [v for v in all_vals if not q or q_lower in v.lower()][:15]
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
        return jsonify(data)
    except Exception as e:
        app.logger.error(f"API error in workitems overview: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


@app.route("/api/export/workitems/csv")
@require_permission('workitems.view')
def export_workitems_csv():
    """Export workitems as CSV. Supports optional doc fields, audit history, and images.
    Query params:
      - Same filters as /api/workitems (prcfW, search, status, tag, startDate, endDate, priority, assignedUser)
      - include: comma-separated extras: 'fields', 'history', 'images'
      - ids: comma-separated workitem IDs to restrict export (for bulk selection)
    """
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401

    include_set = set(request.args.get('include', '').split(','))
    include_fields  = 'fields'  in include_set and has_permission('workitems.details.view.fields')
    include_history = 'history' in include_set and has_permission('workitems.details.view.audit')
    include_images  = 'images'  in include_set and has_permission('workitems.details.view.images')

    ids_param = request.args.get('ids', '').strip()
    specific_ids = set(int(i) for i in ids_param.split(',') if i.strip().isdigit()) if ids_param else set()

    try:
        result = _get_workitems_data(request.args, export_all=True)
        workitems = result.get('workitems', [])
    except Exception as e:
        app.logger.error(f"Export: failed to fetch workitems: {e}")
        return jsonify({"error": "Failed to fetch workitems"}), 500

    if specific_ids:
        workitems = [w for w in workitems if w['workitemid'] in specific_ids]

    if not workitems:
        output = io.StringIO()
        output.write('No workitems to export\r\n')
        resp = make_response(output.getvalue())
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
        resp.headers['Content-Disposition'] = 'attachment; filename=workitems_export.csv'
        return resp

    domains = {}
    for w in workitems:
        wid = w['workitemid']
        try:
            domains[wid] = get_domain_for_workitem(wid)
        except Exception:
            domains[wid] = OCTO_DOMAIN

    _include_fields  = include_fields
    _include_history = include_history
    _include_images  = include_images
    _app = app

    def _fetch(wid):
        detail = {'fields': {}, 'history': [], 'images': []}
        domain = domains.get(wid, OCTO_DOMAIN)
        with _app.app_context():
            if _include_fields or _include_images:
                try:
                    urls, extensions = [], []  # safe defaults
                    cached = cache.get(f"media_info_{wid}")
                    if cached:
                        detail['fields'] = cached.get('fields', {})
                    else:
                        returndata = get_workitemdata_param(wid, domain)
                        if returndata:
                            workitemdata, document_id = returndata
                            extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id, domain)
                            detail['fields'] = fields
                            cache.set(f"media_info_{wid}", {"fields": fields, "media_count": len(urls)})
                            if urls:
                                cache.set(f"media_data_{wid}", {'extensions': extensions, 'urls': urls})
                    if _include_images:
                        cached_media = cache.get(f"media_data_{wid}")
                        if cached_media:
                            urls       = cached_media.get('urls', [])
                            extensions = cached_media.get('extensions', [])
                        for i, (img_url, ext) in enumerate(zip(urls[:5], extensions[:5])):
                            try:
                                img_bytes = get_media(img_url, domain)
                                if str(ext).lower() in ('.tif', '.tiff'):
                                    with Image.open(io.BytesIO(img_bytes)) as img:
                                        if img.mode != 'RGB':
                                            img = img.convert('RGB')
                                        buf = io.BytesIO()
                                        img.save(buf, 'JPEG', quality=75)
                                        img_bytes = buf.getvalue()
                                detail['images'].append(base64.b64encode(img_bytes).decode('utf-8'))
                            except Exception as img_err:
                                _app.logger.warning(f"Export: image {i} for {wid} failed: {img_err}")
                except Exception as e:
                    _app.logger.error(f"Export: doc fields error for {wid}: {e}")

            if _include_history:
                try:
                    cached = cache.get(f"audithistory_{wid}")
                    if cached is not None:
                        detail['history'] = cached
                    else:
                        audit_url = (
                            f'https://{domain}/api/processservice/api/v2.1/processService/'
                            f'WorkItemAudits?WorkItemID={wid}&VerifyAuditSignatures=true'
                        )
                        token = get_access_token(domain)
                        resp = requests.get(audit_url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
                        resp.raise_for_status()
                        audits_data = resp.json()
                        unique_acts = {}
                        for audit in (audits_data.get('Audits', []) if isinstance(audits_data, dict) else []):
                            aid = audit.get('ActivityInstanceID')
                            if aid and aid not in unique_acts:
                                unique_acts[aid] = datetime.fromisoformat(audit['TimeStamp']).strftime("%Y-%m-%d %H:%M:%S")
                        history_list = []
                        total = len(unique_acts)
                        for i, (aid, ts) in enumerate(unique_acts.items()):
                            name = get_activity_type_name(aid, domain)
                            history_list.append({'Activity': name, 'DateTime': ts, 'Step': total - i})
                        cache.set(f"audithistory_{wid}", history_list, timeout=1800)
                        detail['history'] = history_list
                except Exception as e:
                    _app.logger.error(f"Export: history error for {wid}: {e}")
        return wid, detail

    details_map = {}
    if include_fields or include_history or include_images:
        max_workers = min(10, len(workitems))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch, w['workitemid']): w['workitemid'] for w in workitems}
            for future in as_completed(futures, timeout=120):
                try:
                    wid, detail = future.result()
                    details_map[wid] = detail
                except Exception as e:
                    wid = futures[future]
                    app.logger.error(f"Export: future error for {wid}: {e}")
                    details_map[wid] = {'fields': {}, 'history': [], 'images': []}

    # Determine dynamic columns
    all_field_keys = []
    if include_fields:
        seen_keys = set()
        for w in workitems:
            for k in details_map.get(w['workitemid'], {}).get('fields', {}):
                if k not in seen_keys:
                    seen_keys.add(k)
                    all_field_keys.append(k)

    max_images = 0
    if include_images:
        for w in workitems:
            max_images = max(max_images, len(details_map.get(w['workitemid'], {}).get('images', [])))

    # Build CSV
    priority_label = {3: 'High', 2: 'Medium', 1: 'Low'}
    headers = ['Workitem ID', 'Status', 'Stage', 'Last Movement At', 'Priority', 'Tags']
    if include_fields:
        headers.extend(all_field_keys)
    if include_history:
        headers.append('Audit History')
    if include_images:
        headers.extend(f'Image {i+1} (base64)' for i in range(max_images))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for w in workitems:
        wid = w['workitemid']
        detail = details_map.get(wid, {'fields': {}, 'history': [], 'images': []})
        ts = w.get('modifiedat')
        date_str = ts.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ts, 'strftime') else str(ts or '')[:19]

        row = [
            wid,
            w.get('status', ''),
            w.get('current_stage', ''),
            date_str,
            priority_label.get(w.get('priority', 0), ''),
            '; '.join(t['name'] for t in (w.get('tags') or [])),
        ]
        if include_fields:
            fields = detail['fields']
            row.extend(fields.get(k, '') for k in all_field_keys)
        if include_history:
            history = sorted(detail.get('history', []), key=lambda h: h.get('Step', 0), reverse=True)
            row.append('; '.join(f"Step {h['Step']}: {h['Activity']} @ {h['DateTime']}" for h in history))
        if include_images:
            images = detail.get('images', [])
            row.extend(images[i] if i < len(images) else '' for i in range(max_images))
        writer.writerow(row)

    csv_content = output.getvalue()
    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    filename = f'workitems_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response


@app.route("/workitems")
@require_permission('workitems.view')
def workitems_overview():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))

        logged_in_user = session.get('username')
        userid = session.get('userid')

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
        return render_template("workitems_overview.html",
            logged_in_user=logged_in_user,
            userid=userid,
            process_name=process_name,
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
        return render_template('500.html')


ALLOWED_MIME_TYPES = {
    'pdf': ['application/pdf'],
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': ['image/jpeg']
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
    process_name = request.form.get('processName') 

    if file.filename == '':
        flash(_("No file selected for uploading."), 'error')
        return redirect(url_for('workitems_overview'))

    if not process_name:
        flash(_("No target process selected."), 'error')
        return redirect(url_for('workitems_overview'))

    perms = session.get('permissions', [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms
        if perm.startswith(prefix)
    }
    
    if process_name not in allowed_processes:
        flash(_("You do not have permission to import to this process."), 'error')
        return redirect(url_for('workitems_overview'))

    if file and is_file_allowed(file.filename, file.stream):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{session.get('username')}_{filename}" 
        
        UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        PROCESS_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, process_name.replace('.', '_'))
        os.makedirs(PROCESS_UPLOAD_FOLDER, exist_ok=True)

        file_path = os.path.join(PROCESS_UPLOAD_FOLDER, unique_filename)

        try:
            file.save(file_path)
            flash(_("File '{}' successfully imported into {}.").format(filename, process_name), 'success')
        except Exception as e:
            app.logger.error(f"Error saving imported file: {e}")
            flash(_("An error occurred while saving the file."), 'error')
    else:
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

def get_access_token(domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    cache_key = f'octo_access_token_{domain}'
    token = cache.get(cache_key)
    if token:
        return token

    is_mobscn = domain == OCTO_DOMAIN_MOBSCN
    client_id     = OCTO_CLIENT_ID_MOBSCN     if is_mobscn else OCTO_CLIENT_ID
    client_secret = OCTO_CLIENT_SECRET_MOBSCN  if is_mobscn else OCTO_CLIENT_SECRET

    url = f'https://{domain}/auth/connect/token'
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    body = {
        "grant_type": OCTO_GRANT_TYPE,
        "client_id": client_id,
        "client_secret": client_secret
    }

    try:
        response = requests.post(url=url, headers=headers, data=body, timeout=10)
        response.raise_for_status()
        data = response.json()

        timeout = data.get('expires_in', 3000) - 60
        token = data['access_token']
        cache.set(cache_key, token, timeout=timeout)
        return token
    except requests.exceptions.RequestException as e:
        print(f"Error fetching access token: {e}")
        return None

def get_domain_for_workitem(workitem_id):
    cache_key = f'workitem_domain_{workitem_id}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    mobscan_set = set(get_mobscan_clients())
    conn = None
    try:
        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 tp.ClientName + '.' + tp.Name
            FROM t_WorkItems twi
            JOIN t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
            JOIN t_Processes tp ON tp.ID = tai.ProcessID
            WHERE twi.ID = ?
        """, workitem_id)
        row = cursor.fetchone()
        if row and row[0] in mobscan_set:
            domain = OCTO_DOMAIN_MOBSCN
        elif row:
            domain = OCTO_DOMAIN
        else:
            cursor.execute(f"""
                SELECT TOP 1 1 FROM {RUNTIME_TBL_MOBSCAN}t_WorkItems WHERE ID = ?
            """, workitem_id)
            domain = OCTO_DOMAIN_MOBSCN if cursor.fetchone() else OCTO_DOMAIN
        cache.set(cache_key, domain, timeout=3600)
        return domain
    except Exception as e:
        app.logger.error(f"Failed to determine domain for workitem {workitem_id}: {e}")
        return OCTO_DOMAIN
    finally:
        if conn: conn.close()

def get_workitemdata_param(workitem_id, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    url = f'https://{domain}/api/processservice/api/v2.1/processService/WorkItems/{workitem_id}/load'
    access_token = get_access_token(domain)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url=url, headers=headers, timeout=10)
    str_content = json.dumps(response.json())
    base64_bytes = base64.b64encode(str_content.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')

    return base64_string, response.json()['DocumentID']


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

def get_extensions_urls_fields(workitemdata, document_id, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    url = f'https://{domain}/api/documentservice/api/v2.1/documentService/thin/Document/{document_id}?WithExtensions=false&WithDocumentStructure=true&WithTables=false&WithDocumentAudits=true&LoadMediaStreams=true'
    access_token = get_access_token(domain)
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
    # with open('data.json', 'w') as f:
    #     json.dump(doc_json, f)
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

def get_media(url, domain=None):
    if domain is None:
        domain = OCTO_DOMAIN
    access_token = get_access_token(domain)
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

        domain = get_domain_for_workitem(workitem_id)
        returndata = get_workitemdata_param(workitem_id, domain)
        if not returndata:
            return jsonify({"error": _("Workitem not found")}), 404

        workitemdata, document_id = returndata
        extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id, domain)

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
        domain = get_domain_for_workitem(workitem_id)
        media_data = cache.get(f"media_data_{workitem_id}")
        if not media_data:
            returndata = get_workitemdata_param(workitem_id, domain)
            if not returndata:
                return Response(_("Workitem not found"), status=404)

            workitemdata, document_id = returndata
            extensions, urls, fields = get_extensions_urls_fields(workitemdata, document_id, domain)
            media_data = {'extensions': extensions, 'urls': urls}
            cache.set(f"media_data_{workitem_id}", media_data)

        extensions = media_data.get('extensions', [])
        urls = media_data.get('urls', [])

        if media_index >= len(urls):
            return Response(_("Media index out of bounds"), status=404)

        target_url = urls[media_index]
        target_extension = extensions[media_index].lower()

        if target_extension == '.tif':
            _tif_cache_key = f"media_raw_tif_{workitem_id}_{media_index}"
            cached_jpeg = cache.get(_tif_cache_key)
            if cached_jpeg is not None:
                return send_file(io.BytesIO(cached_jpeg), mimetype='image/jpeg', as_attachment=False)

            raw_media_bytes = get_media(target_url, domain)
            try:
                image_stream = io.BytesIO(raw_media_bytes)
                with Image.open(image_stream) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=85)
                    jpeg_bytes = buffer.getvalue()
                    cache.set(_tif_cache_key, jpeg_bytes, timeout=3600)
                    return send_file(io.BytesIO(jpeg_bytes), mimetype='image/jpeg', as_attachment=False)
            except Exception as e:
                print(f"An error occurred during TIFF conversion: {e}")
                return _("Failed to process TIFF image"), 500

        raw_media_bytes = get_media(target_url, domain)
        if target_extension == '.jpg':
            mimetype = 'image/jpeg'
        elif target_extension == '.png':
            mimetype = 'image/png'
        else:
            mimetype = 'application/octet-stream'

        response = make_response(raw_media_bytes)
        response.headers.set('Content-Type', mimetype)
        response.headers.set('Cache-Control', 'private, max-age=3600')
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return Response(_("Internal Server Error"), status=500)

@cache.memoize()
def get_activity_type_name(activity_instance_id: str, domain: str = None) -> str:
    if domain is None:
        domain = OCTO_DOMAIN
    activity_instances_url = f'https://{domain}/api/configurationservice/api/v2.1/configservice/ActivityInstances/{activity_instance_id}'
    access_token = get_access_token(domain)
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
    _cache_key = f"audithistory_{workitem_id}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        domain = get_domain_for_workitem(workitem_id)
        audit_url = f'https://{domain}/api/processservice/api/v2.1/processService/WorkItemAudits?WorkItemID={workitem_id}&VerifyAuditSignatures=true&ExportSignatureVerificationCertificates=true'
        access_token = get_access_token(domain)
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url=audit_url, headers=headers, timeout=10)
        response.raise_for_status()
        audits = response.json()
        if not audits or not isinstance(audits, dict):
            return jsonify([])
        unique_activities = {}
        for audit in audits.get('Audits', []):
            activity_id = audit.get('ActivityInstanceID')
            if activity_id and activity_id not in unique_activities:
                unique_activities[activity_id] = datetime.fromisoformat(audit['TimeStamp']).strftime("%Y-%m-%d %H:%M:%S")

        complete_array = []
        total_steps = len(unique_activities)

        for i, (activity_id, time_stamp) in enumerate(unique_activities.items()):
            activity_name = get_activity_type_name(activity_id, domain)

            step_info = {
                "Activity": activity_name,
                "DateTime": time_stamp,
                "Step": total_steps - i
            }
            complete_array.append(step_info)

        cache.set(_cache_key, complete_array, timeout=1800)
        return jsonify(complete_array)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"{_('Failed to fetch audit history')}: {e}"}), 500
    except Exception as e:
        return jsonify({"error": f"{_('An unexpected error occurred')}: {e}"}), 500

# ------------------------ workitem collaboration apis s----------------------- #
@app.route('/api/users')
def get_users_for_mentions():
    if 'username' not in session:
        return jsonify({"error": _("Not authorized")}), 401

    _all_users = has_permission('admin.interact.users.all')
    _org = session.get('organizationcode', '')
    _cache_key = f"users_mentions_{'all' if _all_users else _org}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        if has_permission('workitems.details.add.comment'):
            if _all_users:
                cursor.execute("""
                SELECT userID, username, fullname FROM Users
                """)
            else:
                cursor.execute("""
                SELECT userID, username, fullname FROM Users
                WHERE organizationcode IN ('SYDC', ?) AND accessid not in (1,2)
                """, _org)
        users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        cache.set(_cache_key, users, timeout=900)
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

    _cache_key = f"interactions_{workitemid}"
    cached = cache.get(_cache_key)
    if cached is not None:
        return jsonify(cached)

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
                    'userID': crow.userID,
                    'userIcon': resolve_user_icon_url(crow.userID)
                })
        result = {
            'priority': priority,
            'assigneduserid': assigneduserid,
            'comments': comments,
            'tags': tags
        }
        cache.set(_cache_key, result, timeout=600)
        return jsonify(result)
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
        conn.commit()

        cursor.execute("SELECT TOP 1 CommentID FROM Workitem_Comments ORDER BY CommentID DESC")
        comment_id = cursor.fetchone()[0]

        mentions = re.findall(r'@(\w+\.\w+)', comment_text)
        if mentions:
            placeholders = ','.join('?' for _ in mentions)
            cursor.execute(f"SELECT userID, username FROM Users WHERE username IN ({placeholders})", mentions)
            mentioned_users = cursor.fetchall()
            for user in mentioned_users:
                cursor.execute("INSERT INTO Comment_Mentions (CommentID, MentionedUserID) VALUES (?, ?)", (comment_id, user.userID))
                notification_link = url_for('workitems_overview', search=workitemid, _external=False)
                create_notification(user.userID, f"{session['username']} mentioned you on workitem {workitemid}", link=notification_link, icon='fa-at')
        conn.commit()
        cache.delete(f"interactions_{workitemid}")
        return jsonify({'success': True, 'message': _("Comment added.")})
    except Exception as e:
        app.logger.error(f"Error adding comment for workitem {workitemid}: {e}")
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
        cache.delete(f"interactions_{workitemid}")
        if assignedUserID != None and assignedUserID != session['userid']:
            notification_link = url_for('workitems_overview', search=workitemid, _external=False)
            create_notification(assignedUserID, f"{session['username']} {_('assigned you on workitem')} {workitemid}", link=notification_link, icon='fa-people-carry-box')
        return jsonify({'success': True, 'message': _("Assignment updated.")})
    except Exception as e:
        app.logger.error(f"Error setting assignment for workitem {workitemid}: {e}")
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
        cache.delete(f"interactions_{workitemid}")
        return jsonify({'success': True, 'message': _("Priority updated.")})
    except Exception as e:
        app.logger.error(f"Error setting priority for workitem {workitemid}: {e}")
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

    cached = cache.get('all_tags')
    if cached is not None:
        return jsonify(cached)

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
        tags = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
        cache.set('all_tags', tags, timeout=1800)
        return jsonify(tags)
    except Exception as e:
        app.logger.error(f"Failed to fetch all tags: {e}")
        return jsonify({"error": _("Could not fetch tags")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/workitems_page_init')
def api_workitems_page_init():
    if 'username' not in session:
        return jsonify({}), 401

    # Tags
    tags = cache.get('all_tags')
    if tags is None:
        conn = None
        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT TagID, TagName, TagColor FROM Tags ORDER BY TagName")
            tags = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
            cache.set('all_tags', tags, timeout=1800)
        except Exception as e:
            app.logger.error(f"page_init: failed to fetch tags: {e}")
            tags = []
        finally:
            if conn: conn.close()

    # Users
    _all_users = has_permission('admin.interact.users.all')
    _org = session.get('organizationcode', '')
    _users_key = f"users_mentions_{'all' if _all_users else _org}"
    users = cache.get(_users_key)
    if users is None:
        conn = None
        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            if has_permission('workitems.details.add.comment'):
                if _all_users:
                    cursor.execute("SELECT userID, username, fullname FROM Users")
                else:
                    cursor.execute("""
                        SELECT userID, username, fullname FROM Users
                        WHERE organizationcode IN ('SYDC', ?) AND accessid not in (1,2)
                    """, _org)
                users = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
            else:
                users = []
            cache.set(_users_key, users, timeout=900)
        except Exception as e:
            app.logger.error(f"page_init: failed to fetch users: {e}")
            users = []
        finally:
            if conn: conn.close()

    perms = session.get('permissions', [])
    prefix = "workitems.filter.process."
    allowed_processes = {
        (perm.split('.')[-2] + '.' + perm.split('.')[-1])
        for perm in perms if perm.startswith(prefix)
    }
    current_lang = str(get_locale())
    _fields_key = f"config_fields_{'_'.join(sorted(allowed_processes))}_{current_lang}"
    field_config = cache.get(_fields_key)
    if field_config is None:
        lang_column_map = {'de': 'GermanLabel', 'fr': 'FrenchLabel', 'it': 'ItalianLabel', 'en': 'EnglishLabel'}
        target_column = lang_column_map.get(current_lang, 'EnglishLabel')
        search_options = {}
        db_labels_map = {}
        conn = None
        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel FROM Search_Field_Labels")
                for row in cursor.fetchall():
                    translated_label = getattr(row, target_column) or row.EnglishLabel
                    db_labels_map[row.FieldKey] = translated_label
            except Exception:
                pass
            cursor.execute("SELECT TOP 0 * FROM SearchConfig")
            cols = [c[0] for c in cursor.description if c[0].startswith('col_')]
            query = f"SELECT ProcessName, {','.join(cols)} FROM SearchConfig"
            cursor.execute(query)
            for row in cursor.fetchall():
                proc_name = row.ProcessName
                if proc_name not in allowed_processes:
                    continue
                fields = []
                for i, col_name in enumerate(cols):
                    if row[i+1]:
                        field_key = col_name.replace('col_', '')
                        nice_label = db_labels_map.get(field_key, field_key.replace('_', ' ').title())
                        fields.append({'value': field_key, 'label': nice_label})
                fields.sort(key=lambda x: x['label'])
                search_options[proc_name] = fields
        except Exception as e:
            app.logger.error(f"page_init: failed to fetch field config: {e}")
        finally:
            if conn: conn.close()
        field_config = {'search_options': search_options, 'labels': db_labels_map}
        cache.set(_fields_key, field_config, timeout=3600)

    return jsonify({'tags': tags, 'users': users, 'field_config': field_config})


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
        cache.delete(f"interactions_{workitemid}")
        cache.delete('all_tags')

        return jsonify({'success': True, 'message': _("Tag added successfully."), 'tag': {'TagID': tag_id, 'TagName': tag_name, 'TagColor': tag_color}})

    except Exception as e:
        app.logger.error(f"Error adding tag to workitem {workitemid}: {e}")
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

        cache.delete(f"interactions_{workitemid}")
        cache.delete('all_tags')
        return jsonify({'success': True, 'message': _("Tag removed successfully.")})
    except Exception as e:
        app.logger.error(f"Error removing tag {tag_id} from workitem {workitemid}: {e}")
        return jsonify({'success': False, 'message': _("An unexpected error occurred.")}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ---------------------- workitem collaboration apis end --------------------- #

# --------------------------- workitem overview end -------------------------- #

def get_all_portal_users(fromRequest, action):
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()

        if has_permission(f'{fromRequest}.{action}'):
            if has_permission('admin.interact.users.all'):
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
        return render_template("profile.html", userid=userid, logged_in_user=logged_in_user, fullname=fullname, email=email, pageV=pageVisability())
    except Exception as e:
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

            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()

            if not re.search("^((?!\.)[\w\-_.]*[^.])(@\w+)(\.\w+(\.\w+)?[^.\W])$", email) or len(email) >= 50:
                flash(_("Email Adress is not valid"), 'failure_updateProfile')
                return redirect(url_for("profile"))
            
            cursor.execute("SELECT 0 FROM Users WHERE Email = ? and userid <> ?", (email, userid))
            row = cursor.fetchone()

            if row:
                flash(_("Email Adress is already in use"), 'failure_updateProfile')
                return redirect(url_for("profile"))
            
            
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
            flash(_("Profile updated successfully!"), 'success_updateProfile')
            return redirect(url_for("profile"))
    except Exception as e:
        flash(_("Unexpected error"), 'failure_updateProfile')
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

                flash(_("Password updated successfully!"), 'success_changePW')
                return redirect(url_for('profile'))
            else:
                flash(_("Current password is incorrect"), 'failure_changePW')
                return redirect(url_for('profile'))
    except Exception as e:
        flash(_("Unexpected Error"), 'failure_changePW')
        return redirect(url_for('profile'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/language/<lang>')
def set_language(lang=None):
    conn = None
    try:
        if lang not in ['de', 'en', 'fr', 'it']:
            flash(_("Unexpected Error"), 'failure_setLanguage')
            return redirect(url_for('profile'))
        userid = session['userid']
        session['locale'] = lang
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE Users SET locale = ? WHERE userid = ?", [lang, userid])
        conn.commit()
        cursor.close()
        flash(_("Language changed successfully!"), 'success_setLanguage')
        return redirect(url_for('profile'))
    except Exception as e:
        app.logger.error(f"set_language error: {e}")
        flash(_("Unexpected Error"), 'failure_setLanguage')
        return redirect(url_for('profile'))
    finally:
        if conn:
            conn.close()

@app.context_processor
def inject_current_lang():
    return {'current_lang': str(get_locale())}

def resolve_user_icon_url(user_id):
    if not user_id:
        return url_for('static', filename='images/default-icon.png')
    
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
        
    return url_for('static', filename='images/default-icon.png')


@app.context_processor
def utility_processor():
    return dict(get_user_icon_url=resolve_user_icon_url)

# -------------------------------- profile end ------------------------------- #

# ---------------------------------- jdvance --------------------------------- #
@app.route('/jdvance')
@require_permission('jd.view')
def jdvance():
    return render_template("jd/jdvance.html")
# -------------------------------- jdvance end ------------------------------- #

# -------------------------------- bexio ------------------------------------- #
def get_allowed_client_details():
    try:
        perms = session.get('permissions', [])
        prefix = "invoices.view."
        allowed_names = sorted({
            perm.split('.')[-1]
            for perm in perms
            if perm.startswith(prefix)
        })

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        clients = []
        
        for name in allowed_names:
            cursor.execute('SELECT bexioClientId, ClientName FROM ClientInvoices WHERE ClientName = ?', (name,))
            row = cursor.fetchone()
            if row:
                clients.append({'id': row[0], 'name': row[1]})
        
        return clients
    except Exception as e:
        app.logger.error(f"Error fetching client details: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def searchBexioInvoices(clientIds, dateFrom, dateTo, search_nr=None, status=None):
    url = "https://api.bexio.com/2.0/kb_invoice/search"
    accessToken = BEXIO_PAT
    if not accessToken:
        app.logger.error("BEXIO_PAT is not set.")
        return []

    headers = {
        'Accept': "application/json",
        'Authorization': f"Bearer {accessToken}",
    }
    all_invoices = []
    for clientId in clientIds:
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
            all_invoices.extend(invoices)

        except requests.exceptions.RequestException as e:
            app.logger.error(f"Bexio API search failed: {e}")
            return []
        except json.JSONDecodeError:
            app.logger.error(f"Bexio API returned invalid JSON.")
            return []
    return all_invoices

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
        return None, None

def map_invoice_status(status_id):
    if status_id == 9:
        return {'text': _('Paid'), 'color': 'green'}
    else:
        return {'text': _('Open'), 'color': 'blue'}

def getBexioClientIds():
    try:
        perms = session.get('permissions', [])
        prefix = "invoices.view."
        allowed_client_invoice_views= sorted({
            perm.split('.')[-1]
            for perm in perms
            if perm.startswith(prefix)
        })

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        clientIds = []
        for aciv in allowed_client_invoice_views:
            cursor.execute('SELECT bexioClientId FROM ClientInvoices WHERE ClientName = ?', aciv)
            row = cursor.fetchone()
            if row: clientIds.append(row[0])
        return clientIds
    except Exception as e:
        print(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
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
        
        clients = get_allowed_client_details()
        search_nr_perm = has_permission('invoices.filter.invoiceid')
        search_nr = request.args.get('search', '') if search_nr_perm else None
        status_perm = has_permission('invoices.filter.status')
        status = request.args.get('status', '') if status_perm else None
        date_perm = has_permission('invoices.filter.date')
        dateFrom = request.args.get('dateFrom',(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')) if date_perm else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        dateTo = request.args.get('dateTo',datetime.now().strftime('%Y-%m-%d')) if date_perm else datetime.now().strftime('%Y-%m-%d')


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
                               ,pageV=pageVisability(),
                               clients=clients)
    except Exception as e:
        return render_template('500.html')

@app.route("/api/invoices")
@require_permission('invoices.view')
def api_invoices():
    try:
        if 'username' not in session:
            return jsonify({"error": _("Not authorized")}), 401
        
        selected_client_id = request.args.get('client_id')
        search_nr = request.args.get('search', '') if has_permission('invoices.filter.invoiceid') else None
        status = request.args.get('status', '')  if has_permission('invoices.filter.status') else None
        dateFrom = request.args.get('dateFrom',(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')) if has_permission('invoices.filter.date') else (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        dateTo = request.args.get('dateTo',datetime.now().strftime('%Y-%m-%d')) if has_permission('invoices.filter.date') else datetime.now().strftime('%Y-%m-%d')

        allowed_ids = getBexioClientIds()
        target_ids = []
        if selected_client_id:
            try:
                sel_id = int(selected_client_id)
                if sel_id in allowed_ids:
                    target_ids = [sel_id]
                else:
                    return jsonify([])
            except ValueError:
                target_ids = allowed_ids 
        else:
            target_ids = allowed_ids 

        if not target_ids:
            return jsonify([])

        invoices_list = searchBexioInvoices(
            clientIds=target_ids,
            dateFrom=dateFrom,
            dateTo=dateTo,
            search_nr=search_nr,
            status=status
        )
        return jsonify(invoices_list)

    except Exception as e:
        return jsonify({"error": "Failed to fetch invoices"}), 500

@app.route("/invoice/<int:invoice_id>/pdf")
@require_permission('invoices.download')
def download_invoice_pdf(invoice_id):
    if 'username' not in session:
        return redirect(url_for("login"))

    try:
        pdf_content, pdf_name = getBexioInvoicePDF(invoice_id)

        if pdf_content and pdf_name:
            return Response(
                pdf_content,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment;filename={pdf_name}'}
            )
        else:
            flash(_("Could not download PDF. File not found or API error."), 'error')
            return redirect(url_for('invoices'))

    except Exception as e:
        app.logger.error(f"Failed to download invoice PDF {invoice_id}: {e}")
        flash(_("An unexpected error occurred while downloading the PDF."), 'error')
        return redirect(url_for('invoices'))
# -------------------------------- invoices end -------------------------------- #
    

@app.route("/chat")
@require_permission('chat.view')
def chat_page():
    if 'username' not in session:
        return redirect(url_for("login"))
    
    portal_users = get_all_portal_users('chat', 'view')
    current_user_id = session.get('userid')
    
    available_users = [u for u in portal_users if str(u['userID']) != str(current_user_id)]
    return render_template("chat.html", 
                         logged_in_user=session.get('username'),
                         userid=current_user_id,
                         available_users=available_users,
                         pageV=pageVisability())

@app.route("/api/chat/conversations")
@require_permission('chat.view')
def get_conversations():
    if 'userid' not in session:
        return jsonify({"error": _("Not authorized")}), 401
        
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                c.ConversationID,
                u.fullname AS OtherUserName,
                u.userID AS OtherUserID,
                c.LastMessageAt,
                (SELECT TOP 1 MessageText FROM Chat_Messages m WHERE m.ConversationID = c.ConversationID ORDER BY Timestamp DESC) as LastMessage,
                (SELECT COUNT(*) FROM Chat_Messages m WHERE m.ConversationID = c.ConversationID AND m.IsRead = 0 AND m.SenderID <> ?) as UnreadCount
            FROM Chat_Conversations c
            JOIN Chat_Participants cp1 ON c.ConversationID = cp1.ConversationID
            JOIN Chat_Participants cp2 ON c.ConversationID = cp2.ConversationID
            JOIN Users u ON cp2.UserID = u.userID
            WHERE cp1.UserID = ? AND cp2.UserID <> ?
            ORDER BY c.LastMessageAt DESC
        """
        userid = session['userid']
        cursor.execute(query, (userid, userid, userid))
        
        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                'id': row.ConversationID,
                'name': row.OtherUserName,
                'other_user_id': row.OtherUserID,
                'last_message': row.LastMessage or _('No messages yet'),
                'last_time': row.LastMessageAt.strftime('%Y-%m-%d %H:%M'),
                'unread': row.UnreadCount,
                'avatar': resolve_user_icon_url(row.OtherUserID)
            })
            
        return jsonify(conversations)
    except Exception as e:
        app.logger.error(f"Error fetching conversations: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route("/api/chat/start/<int:target_user_id>", methods=['POST'])
@require_permission('chat.view')
def start_conversation(target_user_id):
    current_user_id = session['userid']
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        check_query = """
            SELECT cp1.ConversationID 
            FROM Chat_Participants cp1
            JOIN Chat_Participants cp2 ON cp1.ConversationID = cp2.ConversationID
            WHERE cp1.UserID = ? AND cp2.UserID = ?
        """
        cursor.execute(check_query, (current_user_id, target_user_id))
        row = cursor.fetchone()

        if row:
            return jsonify({'success': True, 'conversation_id': row[0]})
            
        cursor.execute("INSERT INTO Chat_Conversations (CreatedAt) OUTPUT INSERTED.ConversationID VALUES (GETDATE())")
        new_conv_id = cursor.fetchone()[0]
        
        cursor.execute("INSERT INTO Chat_Participants (ConversationID, UserID) VALUES (?, ?)", (new_conv_id, current_user_id))
        cursor.execute("INSERT INTO Chat_Participants (ConversationID, UserID) VALUES (?, ?)", (new_conv_id, target_user_id))
        
        conn.commit()
        return jsonify({'success': True, 'conversation_id': new_conv_id})
    except Exception as e:
        app.logger.error(f"Error creating conversation: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route("/api/chat/<int:conversation_id>/messages")
@require_permission('chat.view')
def get_chat_messages(conversation_id):
    userid = session['userid']
    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM Chat_Participants WHERE ConversationID = ? AND UserID = ?", (conversation_id, userid))
        if not cursor.fetchone():
            return jsonify({"error": "Unauthorized"}), 403

        cursor.execute("UPDATE Chat_Messages SET IsRead = 1 WHERE ConversationID = ? AND SenderID <> ?", (conversation_id, userid))
        conn.commit()

        query = """
            SELECT m.MessageID, m.SenderID, m.MessageText, m.Timestamp, u.username
            FROM Chat_Messages m
            JOIN Users u ON m.SenderID = u.userID
            WHERE m.ConversationID = ?
            ORDER BY m.Timestamp ASC
        """
        cursor.execute(query, (conversation_id,))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row.MessageID,
                'is_me': str(row.SenderID) == str(userid),
                'text': row.MessageText,
                'sender': row.username,
                'time': row.Timestamp.strftime('%H:%M'),
                'avatar': resolve_user_icon_url(row.SenderID)
            })
            
        return jsonify(messages)
    except Exception as e:
        app.logger.error(f"Error fetching messages: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@app.route("/api/chat/<int:conversation_id>/send", methods=['POST'])
@require_permission('chat.view')
def send_chat_message(conversation_id):
    data = request.get_json()
    message_text = data.get('message')
    userid = session['userid']
    
    if not message_text:
        return jsonify({'success': False}), 400

    conn = None
    try:
        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM Chat_Participants WHERE ConversationID = ? AND UserID = ?", (conversation_id, userid))
        if not cursor.fetchone():
            return jsonify({"error": "Unauthorized"}), 403

        cursor.execute("""
            INSERT INTO Chat_Messages (ConversationID, SenderID, MessageText) 
            VALUES (?, ?, ?)
        """, (conversation_id, userid, message_text))
        
        cursor.execute("UPDATE Chat_Conversations SET LastMessageAt = GETDATE() WHERE ConversationID = ?", (conversation_id,))
        
        cursor.execute("SELECT UserID FROM Chat_Participants WHERE ConversationID = ? AND UserID <> ?", (conversation_id, userid))
        other_user = cursor.fetchone()
        if other_user:
             workitem_match = re.search(r'/(\d+)', message_text)
             if workitem_match:
                 notif_msg = f"{session['username']} mentioned workitem {workitem_match.group(1)} in chat"
             else:
                 notif_msg = f"New message from {session['username']}"

             notification_link = url_for('chat_page', _external=False)
             create_notification(other_user.UserID, notif_msg, link=notification_link, icon='fa-comments')

        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error sending message: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route("/api/chat/<int:conversation_id>/upload", methods=['POST'])
@require_permission('chat.view')
def upload_chat_file(conversation_id):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    
    file = request.files['file']
    userid = session['userid']

    if file and is_file_allowed(file.filename, file.stream):
        filename = secure_filename(file.filename)
        unique_filename = f"chat_{uuid.uuid4().hex}_{filename}"
        
        upload_path = os.path.join(app.root_path, 'static', 'uploads', 'chat')
        os.makedirs(upload_path, exist_ok=True)
        
        file.save(os.path.join(upload_path, unique_filename))
        
        file_url = url_for('static', filename=f'uploads/chat/{unique_filename}')
        message_text = f"FILE:{filename}|{file_url}"
 
        try:
            conn = engineNexoraDB.raw_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Chat_Messages (ConversationID, SenderID, MessageText) 
                VALUES (?, ?, ?)
            """, (conversation_id, userid, message_text))
            cursor.execute("UPDATE Chat_Conversations SET LastMessageAt = GETDATE() WHERE ConversationID = ?", (conversation_id,))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            if conn: conn.close()
    
    return jsonify({'success': False, 'message': 'Invalid file type'}), 400


# ----------------------------- Generali Evaluation -------------------------- #

@app.route("/generali-dashboard")
@require_permission('generali.dashboard.view')
def generali_evaluation():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali-dashboard.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Error loading Generali Evaluation: {e}")
        return render_template('handlers/500.html'), 500

@app.route("/generali/documents")
@require_permission('generali.documentlist.view')
def generali_documents():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_documents.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability())
    except Exception as e:
        app.logger.error(f"Error loading Generali Documents: {e}")
        return render_template('handlers/500.html'), 500

@app.route("/api/generali/stats")
@require_permission('generali.dashboard.view')
def api_generali_stats():
    conn = None
    try:
        start_date = (request.args.get('startDate')).replace('T',' ')
        end_date = (request.args.get('endDate')).replace('T',' ')

        date_filter = ""
        date_params = []

        if start_date:
            date_filter += " AND DOC_DateCreated >= ?"
            date_params.append(start_date)
        if end_date:
            date_filter += " AND DOC_DateCreated <= ?"
            date_params.append(end_date)

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT
                COUNT(*) as TotalDocs,
                SUM(CASE WHEN DOC_NK1 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_Pass,
                SUM(CASE WHEN DOC_NK2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK2_Pass,
                SUM(CASE WHEN DOC_NK1 = 'keineNachkontrolle' AND DOC_NK2 = 'keineNachkontrolle' THEN 1 ELSE 0 END) as NK1_NK2_Pass
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
        """, date_params)
        kpi_row = cursor.fetchone()
        total = kpi_row[0] or 0
        kpis = {
            "total_docs": total,
            "nk1_rate": round((kpi_row[1] / total) * 100, 1) if total > 0 else 0,
            "nk2_rate": round((kpi_row[2] / total) * 100, 1) if total > 0 else 0,
            "nk1_nk2_rate": round((kpi_row[3] / total) * 100, 1) if total > 0 else 0
        }

        trend_where = "1=1" + date_filter if date_filter else "DOC_DateCreated >= DATEADD(day, -30, GETDATE())"
        cursor.execute(f"""
            SELECT CAST(DOC_DateCreated AS DATE) as d, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE {trend_where}
            GROUP BY CAST(DOC_DateCreated AS DATE)
            ORDER BY d
        """, date_params)
        trend_rows = cursor.fetchall()
        trend_data = {"labels": [str(r[0]) for r in trend_rows], "values": [r[1] for r in trend_rows]}
        
        kpis['avg_daily'] = round(total / len(trend_rows), 1) if total > 0 else 0
        
        cursor.execute(f"""
            SELECT ISNULL(DOC_DOKUMENTENTYP, 'Unknown') as t, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_DOKUMENTENTYP
            ORDER BY c DESC
        """, date_params)
        rows = cursor.fetchall()
        doctype_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(f"""
            SELECT ISNULL(DOC_EMPFAENGER, 'Unknown') as e, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_EMPFAENGER
            ORDER BY c DESC
        """, date_params)
        rows = cursor.fetchall()

        empfaenger_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(f"""
            SELECT ISNULL(DOC_SPRACHE, 'Unknown') as s, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_SPRACHE
            ORDER BY c DESC
        """, date_params)
        rows = cursor.fetchall()

        language_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(f"""
            SELECT ISNULL(DOC_EINGANGSKANAL, 'Unknown') as k, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_EINGANGSKANAL
            ORDER BY c DESC
        """, date_params)
        rows = cursor.fetchall()

        channel_data = {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}

        cursor.execute(f"""
            SELECT ISNULL(DOC_NK1,'Unknown') as nk1, ISNULL(DOC_NK2,'Unknown') as nk2, COUNT(*) as c
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE 1=1 {date_filter}
            GROUP BY DOC_NK1, DOC_NK2
            ORDER BY c DESC
        """, date_params)
        rows = cursor.fetchall()

        nk_data = [{"nk1": r[0], "nk2": r[1], "count": r[2]} for r in rows]
        return jsonify({
            "success": True,
            "kpis": kpis,
            "trend": trend_data,
            "doctype": doctype_data,
            "empfaenger": empfaenger_data,
            "language": language_data,
            "channel": channel_data,
            "nk": nk_data,
        })
    except Exception as e:
        app.logger.error(f"Generali Stats API Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/generali/filter_options")
@require_permission('generali.documentlist.view')
def api_generali_filter_options():
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        result = {}
        for col, key in [
            ("DOC_DOKUMENTENTYP", "doctype"),
            ("DOC_EMPFAENGER", "empfaenger"),
            ("DOC_SPRACHE", "sprache"),
            ("DOC_NK1", "nk1"),
            ("DOC_NK2", "nk2"),
            ("DOC_EINGANGSKANAL", "eingangskanal"),
            ("DOC_KOMMUNIKATION", "kommunikation"),
        ]:
            cursor.execute(f"SELECT DISTINCT {col} FROM [dbo].[v_ReportJobJoinDefinitions] WHERE {col} IS NOT NULL ORDER BY {col}")
            result[key] = [r[0] for r in cursor.fetchall()]
        return jsonify({"success": True, "options": result})
    except Exception as e:
        app.logger.error(f"Generali Filter Options Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/generali/documents")
@require_permission('generali.documentlist.view')
def api_generali_documents():
    conn = None
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('perPage', 40, type=int)
        if per_page not in (40, 100, 200, 500, 1000):
            per_page = 40
        offset = (page - 1) * per_page

        doc_type = request.args.get('docType')
        empfaenger = request.args.get('empfaenger')
        sprache = request.args.get('sprache')
        nk1 = request.args.get('nk1')
        nk2 = request.args.get('nk2')
        eingangskanal = request.args.get('eingangskanal')
        kommunikation = request.args.get('kommunikation')
        start_date = request.args.get('startDate')
        end_date = request.args.get('endDate')
        search = request.args.get('search', '').strip()
        sort_by = request.args.get('sortBy', 'DOC_DateCreated')
        sort_dir = request.args.get('sortDir', 'DESC').upper()
        group_by = request.args.get('groupBy', '')

        allowed_sort_cols = {
            'DOC_DateCreated', 'DOC_DOKUMENTENTYP', 'DOC_EMPFAENGER', 'DOC_SPRACHE',
            'DOC_EINGANGSKANAL', 'DOC_NK1', 'DOC_NK2', 'DOC_BETRAG', 'DOC_KOMMUNIKATION'
        }
        if sort_by not in allowed_sort_cols:
            sort_by = 'DOC_DateCreated'
        if sort_dir not in ('ASC', 'DESC'):
            sort_dir = 'DESC'

        allowed_group_cols = {
            'DOC_DOKUMENTENTYP', 'DOC_EMPFAENGER', 'DOC_SPRACHE', 'DOC_EINGANGSKANAL', 'DOC_KOMMUNIKATION'
        }
        if group_by not in allowed_group_cols:
            group_by = ''

        where_clauses = ["1=1"]
        params = []

        if doc_type:
            where_clauses.append("DOC_DOKUMENTENTYP = ?")
            params.append(doc_type)
        if empfaenger:
            where_clauses.append("DOC_EMPFAENGER = ?")
            params.append(empfaenger)
        if sprache:
            where_clauses.append("DOC_SPRACHE = ?")
            params.append(sprache)
        if nk1:
            where_clauses.append("DOC_NK1 = ?")
            params.append(nk1)
        if nk2:
            where_clauses.append("DOC_NK2 = ?")
            params.append(nk2)
        if eingangskanal:
            where_clauses.append("DOC_EINGANGSKANAL = ?")
            params.append(eingangskanal)
        if kommunikation:
            where_clauses.append("DOC_KOMMUNIKATION = ?")
            params.append(kommunikation)
        if start_date:
            where_clauses.append("DOC_DateCreated >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("DOC_DateCreated <= ?")
            params.append(end_date)
        if search:
            where_clauses.append("""(
                DOC_ID LIKE ? OR CAST(CASE_ID AS NVARCHAR) LIKE ?
                OR DOC_BEZEICHNUNG LIKE ? OR DOC_KONTAKTPERSON LIKE ?
                OR DOC_POLICEN_NR LIKE ? OR DOC_SCHADEN_NR LIKE ?
            )""")
            s = f"%{search}%"
            params.extend([s, s, s, s, s, s])

        where_sql = " AND ".join(where_clauses)

        order_parts = []
        if group_by:
            order_parts.append(f"{group_by} ASC")
        if sort_by != group_by:
            order_parts.append(f"{sort_by} {sort_dir}")
        order_sql = ", ".join(order_parts) if order_parts else "DOC_DateCreated DESC"

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM [dbo].[v_ReportJobJoinDefinitions] WHERE {where_sql}", params)
        total_items = cursor.fetchone()[0]
        total_pages = math.ceil(total_items / per_page)

        cursor.execute(f"""
            SELECT
                DOC_ID, CASE_ID, CASE_FOLDERNAME, DOC_DateCreated, DOC_DOKUMENTENTYP,
                DOC_EMPFAENGER, DOC_SPRACHE, DOC_KOMMUNIKATION, DOC_EINGANGSKANAL,
                DOC_BETRAG, DOC_WAEHRUNG, DOC_NK1, DOC_NK2, DOC_SCANORT,
                DOC_BEZEICHNUNG, DOC_NOTIFIKATIONSSTATUS, DOC_RICHTUNG, DOC_PENDING
            FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE {where_sql}
            ORDER BY {order_sql}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        cols = [
            'doc_id', 'case_id', 'case_foldername', 'doc_datecreated', 'doc_dokumententyp',
            'doc_empfaenger', 'doc_sprache', 'doc_kommunikation', 'doc_eingangskanal',
            'doc_betrag', 'doc_waehrung', 'doc_nk1', 'doc_nk2', 'doc_scanort',
            'doc_bezeichnung', 'doc_notifikationsstatus', 'doc_richtung', 'doc_pending'
        ]
        documents = []
        for row in cursor.fetchall():
            d = dict(zip(cols, row))
            d['doc_datecreated'] = str(d['doc_datecreated']) if d['doc_datecreated'] else None
            documents.append(d)

        return jsonify({
            "success": True,
            "documents": documents,
            "group_by": group_by,
            "pagination": {
                "currentPage": page,
                "totalPages": total_pages,
                "totalItems": total_items,
                "perPage": per_page,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali Documents API Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/generali/documents/<path:doc_id>")
@require_permission('generali.documentlist.view')
def api_generali_document_detail(doc_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM [dbo].[v_ReportJobJoinDefinitions]
            WHERE DOC_ID = ?
        """, [doc_id])
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Not found"}), 404
        cols = [desc[0] for desc in cursor.description]
        doc = {}
        for k, v in zip(cols, row):
            doc[k] = str(v) if v is not None else None
        return jsonify({"success": True, "document": doc})
    except Exception as e:
        app.logger.error(f"Generali Document Detail Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali Reporting --------------------------- #
REPORTING_CATEGORIES = {'export_post', 'export_post_scan', 'provision_archive', 'stray_document_digital', 'stray_document_physical'}
@app.route("/generali/reporting")
@require_permission('generali.reporting.view')
def generali_reporting():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_reporting.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability(),
                               organizationcode=session.get('organizationcode'),
                               can_add=has_permission('generali.reporting.add'),
                               can_edit=has_permission('generali.reporting.edit') or has_permission('generali.reporting.edit.transorganizational'),
                               can_edit_transorg=has_permission('generali.reporting.edit.transorganizational'))
    except Exception as e:
        app.logger.error(f"Error loading Generali Reporting: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/reporting", methods=["GET"])
@require_permission('generali.reporting.view')
def api_generali_reporting_list():
    conn = None
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get('startDate', '').strip()
        end_date   = request.args.get('endDate', '').strip()
        category   = request.args.get('category', '').strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ReportForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ReportForDate <= ?")
            params.append(end_date)
        if category and category in REPORTING_CATEGORIES:
            where_clauses.append("category = ?")
            params.append(category)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*) FROM [dbo].[reportingiss] {where_sql}", params)
        total_records = cursor.fetchone()[0]
        total_pages = max(1, -(-total_records // per_page))

        cursor.execute(f"""
            SELECT ID, ReportForDate, ReportTimeStamp, ReportByUserID, ontime, category
                   --,EmailReceivedTimeStamp, DeliveryTimeStamp, LatestDeliveryTimeStamp, MailRoomRequestTimeStamp
            FROM [dbo].[reportingiss]
            {where_sql}
            ORDER BY ReportForDate DESC, ReportTimeStamp DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[3] for r in rows if r[3] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engineNexoraDB.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {'fullname': fullname, 'orgCode': orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                app.logger.warning(f"User lookup failed for reporting: {ue}")


        records = []
        for r in rows:
            # , email_rcvd, delivery_ts, latest_ts, mailroom_ts
            rec_id, report_date, report_ts, user_id, ontime, cat = r
            user_info = user_map.get(user_id, {})
            records.append({
                'id':                      rec_id,
                'reportForDate':           str(report_date) if report_date else None,
                'reportTimeStamp':         report_ts.isoformat() if report_ts else None,
                'reportByUserID':          user_id,
                'fullname':                user_info.get('fullname'),
                'orgCode':                 user_info.get('orgCode'),
                'ontime':                  bool(ontime),
                'category':                cat

            })
            # 'emailReceivedTimeStamp':   email_rcvd.isoformat() if email_rcvd else None,
            #     'deliveryTimeStamp':        delivery_ts.isoformat() if delivery_ts else None,
            #     'latestDeliveryTimeStamp':  latest_ts.isoformat() if latest_ts else None,
            #     'mailRoomRequestTimeStamp': mailroom_ts.isoformat() if mailroom_ts else None,

        return jsonify({
            'success': True,
            'records': records,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali Reporting List Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/reporting", methods=["POST"])
@require_permission('generali.reporting.add')
def api_generali_reporting_add():
    conn = None
    try:
        body = request.get_json(force=True)
        report_for_date   = body.get('reportForDate', '').strip()
        category          = body.get('category', '').strip()
        ontime            = bool(body.get('ontime', False))
        user_id           = session.get('userid')
        # email_received    = body.get('emailReceivedTimeStamp') or None
        # mailroom_request  = body.get('mailRoomRequestTimeStamp') or None
        # delivery          = body.get('deliveryTimeStamp') or None
        # latest_delivery   = body.get('latestDeliveryTimeStamp') or None

        # email_received   = email_received.replace('T',' ') if email_received else None
        # mailroom_request = mailroom_request.replace('T',' ') if mailroom_request else None
        # delivery         = delivery.replace('T',' ') if delivery else None
        # latest_delivery  = latest_delivery.replace('T',' ') if latest_delivery else None

        
        if not report_for_date:
            return jsonify({"success": False, "error": "reportForDate is required"}), 400
        if category not in REPORTING_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        multi_allowed = {'provision_archive', 'stray_document_digital', 'stray_document_physical'}
        if category not in multi_allowed:
            cursor.execute("""
                SELECT COUNT(*) FROM [dbo].[reportingiss]
                WHERE ReportForDate = ? AND ReportByUserID = ? AND category = ?
            """, [report_for_date, user_id, category])
            if cursor.fetchone()[0] > 0:
                return jsonify({"success": False, "error": "A report for this date and category already exists."}), 409

        cursor.execute("""
            INSERT INTO [dbo].[reportingiss]
                (ReportForDate, ReportTimeStamp, ReportByUserID, ontime, category
                 --,EmailReceivedTimeStamp, DeliveryTimeStamp, LatestDeliveryTimeStamp, MailRoomRequestTimeStamp
                       )
            VALUES (?, GETDATE(), ?, ?, ?)
        """, [report_for_date, user_id, 1 if ontime else 0, category
            #   ,email_received, delivery, latest_delivery, mailroom_request
            ])
        conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Reporting Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/reporting", methods=["PUT"])
@require_any_permission('generali.reporting.edit', 'generali.reporting.edit.transorganizational')
def api_generali_reporting_edit():
    conn = None
    try:
        body            = request.get_json(force=True)
        record_id       = body.get('id')
        report_for_date = (body.get('reportForDate') or '').strip()
        ontime          = bool(body.get('ontime', False))
        # email_received  = body.get('emailReceivedTimeStamp') or None
        # mailroom_req    = body.get('mailRoomRequestTimeStamp') or None
        # delivery        = body.get('deliveryTimeStamp') or None
        # latest_delivery = body.get('latestDeliveryTimeStamp') or None

        if not record_id or not report_for_date:
            return jsonify({"success": False, "error": "id and reportForDate are required"}), 400

        # if email_received:  email_received  = email_received.replace('T', ' ')
        # if mailroom_req:    mailroom_req    = mailroom_req.replace('T', ' ')
        # if delivery:        delivery        = delivery.replace('T', ' ')
        # if latest_delivery: latest_delivery = latest_delivery.replace('T', ' ')

        conn   = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.reporting.edit.transorganizational'):
            _check_generali_record_org(cursor, '[dbo].[reportingiss]', 'ReportByUserID', record_id)
        cursor.execute("""
            UPDATE [dbo].[reportingiss]
            SET ReportForDate            = ?,
                ontime                   = ?
                --,EmailReceivedTimeStamp   = ?,
                --MailRoomRequestTimeStamp = ?,
                --DeliveryTimeStamp        = ?,
                --LatestDeliveryTimeStamp  = ?
            WHERE ID = ?
        """, [report_for_date, 1 if ontime else 0,
            #   email_received, mailroom_req, delivery, latest_delivery,
              record_id])
        conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Reporting Edit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/reporting/<int:record_id>", methods=["DELETE"])
@require_any_permission('generali.reporting.edit', 'generali.reporting.edit.transorganizational')
def api_generali_reporting_delete(record_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.reporting.edit.transorganizational'):
            _check_generali_record_org(cursor, '[dbo].[reportingiss]', 'ReportByUserID', record_id)
        cursor.execute("DELETE FROM [dbo].[reportingiss] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Reporting Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali Additional Services -------------------------- #
@app.route("/generali/additionalServices")
@require_permission('generali.additionalservices.view')
def generali_additionalServices():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_additionalservices.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability(),
                               organizationcode=session.get('organizationcode'),
                               can_add=has_permission('generali.attendance.add'),
                               can_edit=has_permission('generali.attendance.edit') or has_permission('generali.attendance.edit.transorganizational'),
                               can_edit_transorg=has_permission('generali.attendance.edit.transorganizational'),
                               can_add_for_org=has_permission('generali.attendance.addForOrg'))
    except Exception as e:
        app.logger.error(f"Error loading Generali Attendance: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/attendance/categories", methods=["GET"])
@require_permission('generali.additionalservices.view')
def api_generali_attendance_categories():
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, SubCategory
            FROM [Generali].[dbo].[AdditionalServices]
            ORDER BY ParentCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        grouped = {}
        for parent, sub in rows:
            if parent not in grouped:
                grouped[parent] = []
            if sub:
                grouped[parent].append(sub)

        locale = str(get_locale() or 'de').split('_')[0]
        translations = {}
        if locale != 'de':
            cursor2 = conn.cursor()
            cursor2.execute("""
                SELECT OriginalValue, TranslatedValue
                FROM [Generali].[dbo].[CategoryTranslation] WITH (NOLOCK)
                WHERE SourceTable = 'AdditionalServices' AND Locale = ?
            """, [locale])
            for orig, trans in cursor2.fetchall():
                translations[orig] = trans
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        app.logger.error(f"Generali Attendance Categories Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/attendance/orgUsers", methods=["GET"])
@require_permission('generali.attendance.addForOrg')
def api_generali_attendance_org_users():
    conn = None
    try:
        org_code = session.get('organizationcode')
        if not org_code:
            return jsonify({"success": False, "error": "No organization on session"}), 400

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT userid, fullname FROM Users WHERE organizationcode = ? ORDER BY fullname",
            [org_code]
        )
        users = [{'userId': row[0], 'fullname': row[1]} for row in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        app.logger.error(f"Generali Attendance OrgUsers Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/attendance", methods=["GET"])
@require_permission('generali.additionalservices.view')
def api_generali_attendance_list():
    conn = None
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date     = request.args.get('startDate', '').strip()
        end_date       = request.args.get('endDate', '').strip()
        parent_cat     = request.args.get('parentCategory', '').strip()
        sub_cat        = request.args.get('subCategory', '').strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ForDate <= ?")
            params.append(end_date)
        if parent_cat:
            where_clauses.append("ParentCategory = ?")
            params.append(parent_cat)
        if sub_cat:
            where_clauses.append("SubCategory = ?")
            params.append(sub_cat)

        if not has_permission('generali.attendance.edit') and not has_permission('generali.attendance.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[Attendance] {where_sql}", params)
        agg = cursor.fetchone()
        total_records = agg[0] or 0
        total_hours   = float(agg[1]) if agg[1] is not None else 0.0
        total_pages   = max(1, -(-total_records // per_page))

        cursor.execute(f"""
            SELECT ID, EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime
            FROM [Generali].[dbo].[Attendance]
            {where_sql}
            ORDER BY ForDate DESC, RecordDateTime DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[2] for r in rows if r[2] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engineNexoraDB.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {'fullname': fullname, 'orgCode': orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                app.logger.warning(f"User lookup failed for attendance: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, parent, sub, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append({
                'id':             rec_id,
                'effortInHours':  float(effort) if effort is not None else None,
                'userId':         user_id,
                'fullname':       user_info.get('fullname'),
                'orgCode':        user_info.get('orgCode'),
                'forDate':        str(for_date) if for_date else None,
                'parentCategory': parent,
                'subCategory':    sub,
                'recordDateTime': recorded_at.isoformat() if recorded_at else None,
            })

        return jsonify({
            'success': True,
            'records': records,
            'totalHours': total_hours,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali Attendance List Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/attendance", methods=["POST"])
@require_permission('generali.attendance.add')
def api_generali_attendance_add():
    conn = None
    try:
        body          = request.get_json(force=True)
        for_date      = body.get('forDate', '').strip()
        parent_cat    = body.get('parentCategory', '').strip()
        sub_cat_raw   = body.get('subCategory')
        sub_cat       = sub_cat_raw.strip() if sub_cat_raw else None
        effort        = body.get('effortInHours')
        caller_id     = session.get('userid')
        target_raw    = body.get('userId')
        user_id       = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            if not has_permission('generali.attendance.addForOrg'):
                raise PermissionDenied()
            try:
                target_id = int(target_raw)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid userId"}), 400

            nx_conn = engineNexoraDB.raw_connection()
            nx_cur = nx_conn.cursor()
            nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [target_id])
            row = nx_cur.fetchone()
            nx_cur.close()
            nx_conn.close()
            if not row or row[0] != session.get('organizationcode'):
                return jsonify({"success": False, "error": "Target user not in your organization"}), 403
            user_id = target_id

        if not for_date or not parent_cat or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO [Generali].[dbo].[Attendance]
                (EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """, [effort, user_id, for_date, parent_cat, sub_cat])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Attendance Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/attendance/<int:record_id>", methods=["PUT"])
@require_any_permission('generali.attendance.edit', 'generali.attendance.edit.transorganizational')
def api_generali_attendance_edit(record_id):
    conn = None
    try:
        body       = request.get_json(force=True)
        for_date   = body.get('forDate', '').strip()
        parent_cat = body.get('parentCategory', '').strip()
        sub_cat_raw = body.get('subCategory')
        sub_cat    = sub_cat_raw.strip() if sub_cat_raw else None
        effort     = body.get('effortInHours')

        if not for_date or not parent_cat or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.attendance.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[Attendance]', 'UserID', record_id)
        cursor.execute("""
            UPDATE [Generali].[dbo].[Attendance]
            SET ForDate = ?, ParentCategory = ?, SubCategory = ?, EffortInHours = ?
            WHERE ID = ?
        """, [for_date, parent_cat, sub_cat, effort, record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Attendance Edit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/attendance/<int:record_id>", methods=["DELETE"])
@require_any_permission('generali.attendance.edit', 'generali.attendance.edit.transorganizational')
def api_generali_attendance_delete(record_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.attendance.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[Attendance]', 'UserID', record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[Attendance] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Attendance Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali Base Services ----------------------- #
@app.route("/generali/baseServices")
@require_permission('generali.baseservices.view')
def generali_baseServices():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_baseservices.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability(),
                               organizationcode=session.get('organizationcode'),
                               can_add=has_permission('generali.baseservices.add'),
                               can_edit=has_permission('generali.baseservices.edit') or has_permission('generali.baseservices.edit.transorganizational'),
                               can_edit_transorg=has_permission('generali.baseservices.edit.transorganizational'),
                               can_add_for_org=has_permission('generali.baseservices.addForOrg'))
    except Exception as e:
        app.logger.error(f"Error loading Generali Base Services: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/baseservices/orgUsers", methods=["GET"])
@require_permission('generali.baseservices.addForOrg')
def api_generali_baseservices_org_users():
    conn = None
    try:
        org_code = session.get('organizationcode')
        if not org_code:
            return jsonify({"success": False, "error": "No organization on session"}), 400

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT userid, fullname FROM Users WHERE organizationcode = ? ORDER BY fullname",
            [org_code]
        )
        users = [{'userId': row[0], 'fullname': row[1]} for row in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        app.logger.error(f"Generali Base Services OrgUsers Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/baseservices", methods=["GET"])
@require_permission('generali.baseservices.view')
def api_generali_baseservices_list():
    conn = None
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get('startDate', '').strip()
        end_date   = request.args.get('endDate', '').strip()
        category   = request.args.get('category', '').strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ForDate <= ?")
            params.append(end_date)
        if category:
            where_clauses.append("Category = ?")
            params.append(category)

        if not has_permission('generali.baseservices.edit') and not has_permission('generali.baseservices.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[BaseServices] {where_sql}", params)
        agg = cursor.fetchone()
        total_records = agg[0] or 0
        total_hours   = float(agg[1]) if agg[1] is not None else 0.0
        total_pages   = max(1, -(-total_records // per_page))

        cursor.execute(f"""
            SELECT ID, EffortInHours, UserID, ForDate, Category, RecordDateTime
            FROM [Generali].[dbo].[BaseServices]
            {where_sql}
            ORDER BY ForDate DESC, RecordDateTime DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[2] for r in rows if r[2] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engineNexoraDB.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {'fullname': fullname, 'orgCode': orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                app.logger.warning(f"User lookup failed for base services: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, category_val, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append({
                'id':            rec_id,
                'effortInHours': float(effort) if effort is not None else None,
                'userId':        user_id,
                'fullname':      user_info.get('fullname'),
                'orgCode':       user_info.get('orgCode'),
                'forDate':       str(for_date) if for_date else None,
                'category':      category_val,
                'recordDateTime': recorded_at.isoformat() if recorded_at else None,
            })

        return jsonify({
            'success': True,
            'records': records,
            'totalHours': total_hours,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali Base Services List Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


VALID_BASE_CATEGORIES = {"Physical Mailroom, AVOR & Scanning", "Nk1 & NK2", "POE / PPR"}


@app.route("/api/generali/baseservices", methods=["POST"])
@require_permission('generali.baseservices.add')
def api_generali_baseservices_add():
    conn = None
    try:
        body       = request.get_json(force=True)
        for_date   = body.get('forDate', '').strip()
        category   = body.get('category', '').strip()
        effort     = body.get('effortInHours')
        caller_id  = session.get('userid')
        target_raw = body.get('userId')
        user_id    = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            if not has_permission('generali.baseservices.addForOrg'):
                raise PermissionDenied()
            try:
                target_id = int(target_raw)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid userId"}), 400

            nx_conn = engineNexoraDB.raw_connection()
            nx_cur = nx_conn.cursor()
            nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [target_id])
            row = nx_cur.fetchone()
            nx_cur.close()
            nx_conn.close()
            if not row or row[0] != session.get('organizationcode'):
                return jsonify({"success": False, "error": "Target user not in your organization"}), 403
            user_id = target_id

        if not for_date or not category or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if category not in VALID_BASE_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO [Generali].[dbo].[BaseServices]
                (EffortInHours, UserID, ForDate, Category, RecordDateTime)
            VALUES (?, ?, ?, ?, GETDATE())
        """, [effort, user_id, for_date, category])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Base Services Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/baseservices/<int:record_id>", methods=["PUT"])
@require_any_permission('generali.baseservices.edit', 'generali.baseservices.edit.transorganizational')
def api_generali_baseservices_edit(record_id):
    conn = None
    try:
        body     = request.get_json(force=True)
        for_date = body.get('forDate', '').strip()
        category = body.get('category', '').strip()
        effort   = body.get('effortInHours')

        if not for_date or not category or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if category not in VALID_BASE_CATEGORIES:
            return jsonify({"success": False, "error": "Invalid category"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.baseservices.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[BaseServices]', 'UserID', record_id)
        cursor.execute("""
            UPDATE [Generali].[dbo].[BaseServices]
            SET ForDate = ?, Category = ?, EffortInHours = ?
            WHERE ID = ?
        """, [for_date, category, effort, record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Base Services Edit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/baseservices/<int:record_id>", methods=["DELETE"])
@require_any_permission('generali.baseservices.edit', 'generali.baseservices.edit.transorganizational')
def api_generali_baseservices_delete(record_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.baseservices.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[BaseServices]', 'UserID', record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[BaseServices] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Base Services Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali Project Management ------------------ #
@app.route("/generali/projectManagement")
@require_permission('generali.projectmanagement.view')
def generali_projectManagement():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_projectmanagement.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability(),
                               organizationcode=session.get('organizationcode'),
                               can_add=has_permission('generali.projectmanagement.add'),
                               can_edit=has_permission('generali.projectmanagement.edit') or has_permission('generali.projectmanagement.edit.transorganizational'),
                               can_edit_transorg=has_permission('generali.projectmanagement.edit.transorganizational'),
                               can_add_for_org=has_permission('generali.projectmanagement.addForOrg'))
    except Exception as e:
        app.logger.error(f"Error loading Generali Project Management: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/projectmanagement/orgUsers", methods=["GET"])
@require_permission('generali.projectmanagement.addForOrg')
def api_generali_projectmanagement_org_users():
    conn = None
    try:
        org_code = session.get('organizationcode')
        if not org_code:
            return jsonify({"success": False, "error": "No organization on session"}), 400

        conn = engineNexoraDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT userid, fullname FROM Users WHERE organizationcode = ? ORDER BY fullname",
            [org_code]
        )
        users = [{'userId': row[0], 'fullname': row[1]} for row in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        app.logger.error(f"Generali Project Management OrgUsers Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/projectmanagement", methods=["GET"])
@require_permission('generali.projectmanagement.view')
def api_generali_projectmanagement_list():
    conn = None
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date = request.args.get('startDate', '').strip()
        end_date   = request.args.get('endDate', '').strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ForDate <= ?")
            params.append(end_date)

        if not has_permission('generali.projectmanagement.edit') and not has_permission('generali.projectmanagement.edit.transorganizational'):
            where_clauses.append("UserID = ?")
            params.append(session.get('userid'))

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*), SUM(EffortInHours) FROM [Generali].[dbo].[ProjectManagement] {where_sql}", params)
        agg = cursor.fetchone()
        total_records = agg[0] or 0
        total_hours   = float(agg[1]) if agg[1] is not None else 0.0
        total_pages   = max(1, -(-total_records // per_page))

        cursor.execute(f"""
            SELECT ID, EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime
            FROM [Generali].[dbo].[ProjectManagement]
            {where_sql}
            ORDER BY ForDate DESC, RecordDateTime DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[2] for r in rows if r[2] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engineNexoraDB.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {'fullname': fullname, 'orgCode': orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                app.logger.warning(f"User lookup failed for project management: {ue}")

        records = []
        for r in rows:
            rec_id, effort, user_id, for_date, category_val, comment, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append({
                'id':            rec_id,
                'effortInHours': float(effort) if effort is not None else None,
                'userId':        user_id,
                'fullname':      user_info.get('fullname'),
                'orgCode':       user_info.get('orgCode'),
                'forDate':       str(for_date) if for_date else None,
                'category':      category_val,
                'comment':       comment,
                'recordDateTime': recorded_at.isoformat() if recorded_at else None,
            })

        return jsonify({
            'success': True,
            'records': records,
            'totalHours': total_hours,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali Project Management List Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/projectmanagement", methods=["POST"])
@require_permission('generali.projectmanagement.add')
def api_generali_projectmanagement_add():
    conn = None
    try:
        body       = request.get_json(force=True)
        for_date   = body.get('forDate', '').strip()
        effort     = body.get('effortInHours')
        comment    = body.get('comment')
        comment    = comment.strip() if comment else None
        caller_id  = session.get('userid')
        target_raw = body.get('userId')
        user_id    = caller_id

        if target_raw is not None and str(target_raw) != str(caller_id):
            if not has_permission('generali.projectmanagement.addForOrg'):
                raise PermissionDenied()
            try:
                target_id = int(target_raw)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid userId"}), 400

            nx_conn = engineNexoraDB.raw_connection()
            nx_cur = nx_conn.cursor()
            nx_cur.execute("SELECT organizationcode FROM Users WHERE userid = ?", [target_id])
            row = nx_cur.fetchone()
            nx_cur.close()
            nx_conn.close()
            if not row or row[0] != session.get('organizationcode'):
                return jsonify({"success": False, "error": "Target user not in your organization"}), 403
            user_id = target_id

        if not for_date or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO [Generali].[dbo].[ProjectManagement]
                (EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """, [effort, user_id, for_date, 'Project Effort', comment])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Project Management Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/projectmanagement/<int:record_id>", methods=["PUT"])
@require_any_permission('generali.projectmanagement.edit', 'generali.projectmanagement.edit.transorganizational')
def api_generali_projectmanagement_edit(record_id):
    conn = None
    try:
        body     = request.get_json(force=True)
        for_date = body.get('forDate', '').strip()
        effort   = body.get('effortInHours')
        comment  = body.get('comment')
        comment  = comment.strip() if comment else None

        if not for_date or effort is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            effort = float(effort)
            if effort <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid effort value"}), 400

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.projectmanagement.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[ProjectManagement]', 'UserID', record_id)
        cursor.execute("""
            UPDATE [Generali].[dbo].[ProjectManagement]
            SET ForDate = ?, EffortInHours = ?, Comment = ?
            WHERE ID = ?
        """, [for_date, effort, comment, record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Project Management Edit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/projectmanagement/<int:record_id>", methods=["DELETE"])
@require_any_permission('generali.projectmanagement.edit', 'generali.projectmanagement.edit.transorganizational')
def api_generali_projectmanagement_delete(record_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.projectmanagement.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[ProjectManagement]', 'UserID', record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[ProjectManagement] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali Project Management Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ----------------------------- Generali PDQM -------------------------------- #
@app.route("/generali/pdqm")
@require_permission('generali.pdqm.view')
def generali_pdqm():
    try:
        if 'username' not in session:
            return redirect(url_for("login"))
        return render_template("generali_pdqm.html",
                               logged_in_user=session.get('username'),
                               userid=session.get('userid'),
                               pageV=pageVisability(),
                               organizationcode=session.get('organizationcode'),
                               can_add=has_permission('generali.pdqm.add'),
                               can_edit=has_permission('generali.pdqm.edit') or has_permission('generali.pdqm.edit.transorganizational'),
                               can_edit_transorg=has_permission('generali.pdqm.edit.transorganizational'))
    except Exception as e:
        app.logger.error(f"Error loading Generali PDQM: {e}")
        return render_template('handlers/500.html'), 500


@app.route("/api/generali/pdqm/categories", methods=["GET"])
@require_permission('generali.pdqm.view')
def api_generali_pdqm_categories():
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ParentCategory, ParentSubCategory, SubCategory
            FROM [Generali].[dbo].[PDQMMapping]
            ORDER BY ParentCategory, ParentSubCategory, SubCategory
        """)
        rows = cursor.fetchall()
        cursor.close()

        # nested: { parent: { parentSub_or_"": [sub, ...] } }
        grouped = {}
        for parent, parent_sub, sub in rows:
            if parent not in grouped:
                grouped[parent] = {}
            key = parent_sub if parent_sub is not None else ""
            if key not in grouped[parent]:
                grouped[parent][key] = []
            if sub:
                grouped[parent][key].append(sub)

        locale = str(get_locale() or 'de').split('_')[0]
        translations = {}
        if locale != 'de':
            cursor2 = conn.cursor()
            cursor2.execute("""
                SELECT OriginalValue, TranslatedValue
                FROM [Generali].[dbo].[CategoryTranslation] WITH (NOLOCK)
                WHERE SourceTable = 'PDQMMapping' AND Locale = ?
            """, [locale])
            for orig, trans in cursor2.fetchall():
                translations[orig] = trans
            cursor2.close()

        return jsonify({"success": True, "categories": grouped, "translations": translations})
    except Exception as e:
        app.logger.error(f"Generali PDQM Categories Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/pdqm", methods=["GET"])
@require_permission('generali.pdqm.view')
def api_generali_pdqm_list():
    conn = None
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 20
        offset = (page - 1) * per_page

        start_date     = request.args.get('startDate', '').strip()
        end_date       = request.args.get('endDate', '').strip()
        parent_cat     = request.args.get('parentCategory', '').strip()
        parent_sub_cat = request.args.get('parentSubCategory', None)  # None = not filtered; "" = IS NULL
        sub_cat        = request.args.get('subCategory', '').strip()

        where_clauses = []
        params = []

        if start_date:
            where_clauses.append("ForDate >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("ForDate <= ?")
            params.append(end_date)
        if parent_cat:
            where_clauses.append("ParentCategory = ?")
            params.append(parent_cat)
        if parent_sub_cat is not None:
            if parent_sub_cat == "":
                where_clauses.append("ParentSubCategory IS NULL")
            else:
                where_clauses.append("ParentSubCategory = ?")
                params.append(parent_sub_cat)
        if sub_cat:
            where_clauses.append("SubCategory = ?")
            params.append(sub_cat)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(*), SUM(Quantity) FROM [Generali].[dbo].[PDQMReport] {where_sql}", params)
        agg = cursor.fetchone()
        total_records   = agg[0] or 0
        total_quantity  = int(agg[1]) if agg[1] is not None else 0
        total_pages     = max(1, -(-total_records // per_page))

        cursor.execute(f"""
            SELECT ID, Quantity, UserID, ForDate, ParentCategory, ParentSubCategory, SubCategory, RecordDateTime
            FROM [Generali].[dbo].[PDQMReport]
            {where_sql}
            ORDER BY ForDate DESC, RecordDateTime DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, params + [offset, per_page])

        rows = cursor.fetchall()
        cursor.close()

        user_ids = list({r[2] for r in rows if r[2] is not None})
        user_map = {}
        if user_ids:
            try:
                nx_conn = engineNexoraDB.raw_connection()
                nx_cur = nx_conn.cursor()
                placeholders = ','.join(['?'] * len(user_ids))
                nx_cur.execute(
                    f"SELECT userid, fullname, organizationcode FROM Users WHERE userid IN ({placeholders})",
                    user_ids
                )
                for uid, fullname, orgcode in nx_cur.fetchall():
                    user_map[uid] = {'fullname': fullname, 'orgCode': orgcode}
                nx_cur.close()
                nx_conn.close()
            except Exception as ue:
                app.logger.warning(f"User lookup failed for PDQM: {ue}")

        records = []
        for r in rows:
            rec_id, qty, user_id, for_date, parent, parent_sub, sub, recorded_at = r
            user_info = user_map.get(user_id, {})
            records.append({
                'id':                rec_id,
                'quantity':          int(qty) if qty is not None else None,
                'userId':            user_id,
                'fullname':          user_info.get('fullname'),
                'orgCode':           user_info.get('orgCode'),
                'forDate':           str(for_date) if for_date else None,
                'parentCategory':    parent,
                'parentSubCategory': parent_sub,
                'subCategory':       sub,
                'recordDateTime':    recorded_at.isoformat() if recorded_at else None,
            })

        return jsonify({
            'success': True,
            'records': records,
            'totalQuantity': total_quantity,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
            }
        })
    except Exception as e:
        app.logger.error(f"Generali PDQM List Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/pdqm", methods=["POST"])
@require_permission('generali.pdqm.add')
def api_generali_pdqm_add():
    conn = None
    try:
        body           = request.get_json(force=True)
        for_date       = body.get('forDate', '').strip()
        parent_cat     = body.get('parentCategory', '').strip()
        parent_sub_cat = body.get('parentSubCategory', '')  # "" means NULL
        sub_cat_raw    = body.get('subCategory')
        sub_cat        = sub_cat_raw.strip() if sub_cat_raw else None
        quantity       = body.get('quantity')
        user_id        = session.get('userid')

        if not for_date or not parent_cat or quantity is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid quantity"}), 400

        db_parent_sub = parent_sub_cat if parent_sub_cat != "" else None

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO [Generali].[dbo].[PDQMReport]
                (Quantity, ForDate, UserID, RecordDateTime, ParentCategory, ParentSubCategory, SubCategory)
            VALUES (?, ?, ?, GETDATE(), ?, ?, ?)
        """, [quantity, for_date, user_id, parent_cat, db_parent_sub, sub_cat])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali PDQM Add Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/pdqm/<int:record_id>", methods=["PUT"])
@require_any_permission('generali.pdqm.edit', 'generali.pdqm.edit.transorganizational')
def api_generali_pdqm_edit(record_id):
    conn = None
    try:
        body           = request.get_json(force=True)
        for_date       = body.get('forDate', '').strip()
        parent_cat     = body.get('parentCategory', '').strip()
        parent_sub_cat = body.get('parentSubCategory', '')
        sub_cat_raw    = body.get('subCategory')
        sub_cat        = sub_cat_raw.strip() if sub_cat_raw else None
        quantity       = body.get('quantity')

        if not for_date or not parent_cat or quantity is None:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid quantity"}), 400

        db_parent_sub = parent_sub_cat if parent_sub_cat != "" else None

        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.pdqm.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[PDQMReport]', 'UserID', record_id)
        cursor.execute("""
            UPDATE [Generali].[dbo].[PDQMReport]
            SET ForDate = ?, ParentCategory = ?, ParentSubCategory = ?, SubCategory = ?, Quantity = ?
            WHERE ID = ?
        """, [for_date, parent_cat, db_parent_sub, sub_cat, quantity, record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali PDQM Edit Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/generali/pdqm/<int:record_id>", methods=["DELETE"])
@require_any_permission('generali.pdqm.edit', 'generali.pdqm.edit.transorganizational')
def api_generali_pdqm_delete(record_id):
    conn = None
    try:
        conn = engineGeneraliDB.raw_connection()
        cursor = conn.cursor()
        if not has_permission('generali.pdqm.edit.transorganizational'):
            _check_generali_record_org(cursor, '[Generali].[dbo].[PDQMReport]', 'UserID', record_id)
        cursor.execute("DELETE FROM [Generali].[dbo].[PDQMReport] WHERE ID = ?", [record_id])
        conn.commit()
        cursor.close()

        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Generali PDQM Delete Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/api/dashboard/recent_activity")
@require_permission('dashboard.view')
@cache.cached(timeout=120, key_prefix=lambda: f"recent_activity_{session.get('userid')}_{session.get('process_name_dashboard','all')}")
def api_recent_activity():
    conn = None
    try:
        prefix = "dashboard.filter.process."
        process_name = session.get('process_name_dashboard', 'all')

        perms = session.get('permissions', [])
        allowed_processes = sorted({
            (perm.split('.')[-2] + '.' + perm.split('.')[-1])
            for perm in perms if perm.startswith(prefix)
        })
        target_processes = allowed_processes if process_name == 'all' else (
            [process_name] if process_name in allowed_processes else []
        )

        if not target_processes:
            return jsonify([])

        regular_procs, mobscan_procs = split_processes_by_server(target_processes)

        conn = engineOctoDB.raw_connection()
        cursor = conn.cursor()
        activityinstancesToIgnore = get_activityinstancesToIgnore()

        raw_rows = []  
        for tbl_prefix, procs, domain in [
            ("", regular_procs, OCTO_DOMAIN),
            (RUNTIME_TBL_MOBSCAN, mobscan_procs, OCTO_DOMAIN_MOBSCN),
        ]:
            if not procs:
                continue
            p_params, p_ph, c_ph = get_params_from_process_list(procs)
            query = f"""
                SELECT TOP 3 twi.ID, twi.ModifiedAt, tp.Name as ProcessName
                FROM {tbl_prefix}t_WorkItems twi
                JOIN {tbl_prefix}t_ActivityInstances tai ON twi.ActivityInstanceID = tai.ID
                JOIN {tbl_prefix}t_Processes tp ON tp.ID = tai.ProcessID
                WHERE twi.Status <> 2
                  AND tp.Name IN ({p_ph})
                  AND tp.ClientName IN ({c_ph})
                  AND tai.ActivityInstanceName not in ({activityinstancesToIgnore})
                ORDER BY twi.ModifiedAt DESC
            """
            cursor.execute(query, p_params)
            raw_rows.extend((row, domain) for row in cursor.fetchall())

        raw_rows.sort(key=lambda x: x[0].ModifiedAt, reverse=True)

        activity = []
        for row, domain in raw_rows[:3]:
            workitemdata, doc_id = get_workitemdata_param(row.ID, domain)
            _, _, fields = get_extensions_urls_fields(workitemdata, doc_id, domain)
            fields = {k: v for k, v in fields.items() if v}
            activity.append({
                "id": row.ID,
                "time": row.ModifiedAt.strftime('%H:%M'),
                "process": row.ProcessName,
                "fields": fields
            })

        return jsonify(activity)
    except Exception as e:
        app.logger.error(f"Activity feed error: {e}")
        return jsonify([])
    finally:
        if conn: conn.close()
# ------------------------------- ONLY FOR PROD -------------------------------- # 
# app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/nexora')
# ----------------------------- ONLY FOR PROD end ------------------------------ #


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
