from fileinput import filename
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, Response, make_response, send_file
from flask_babel import Babel, gettext, ngettext
import pyodbc
from pyodbc import DatabaseError
from dotenv import load_dotenv
import os
from datetime import timedelta
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


"""-----------------------Logging-------------------------"""
def log_user_action(action_type, resource_id=None, details=None):
    if 'username' not in session:
        return
    
    try:
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER},1433;'
            f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO User_Logs
            (userID, username, action_type, resource_id, details, ip_address, user_agent, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get('userid'),
            session.get('username'),
            action_type,
            resource_id,
            json.dumps(details) if details else None,
            request.remote_addr,
            request.headers.get('User-Agent', ''),
            session.get('session_id', '')
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        app.logger.error(f"Failed to log user action '{action_type}': {e}")

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

app = Flask(__name__)
babel = Babel(app, locale_selector=get_locale, timezone_selector=get_timezone)
load_dotenv()

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
DB_SERVER = os.environ.get("DB_SERVER")
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


@app.route("/signin")
def signin():
    return render_template("seperate_page_login.html")

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

@app.route("/login/<page>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login(page=None):
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        REMEMBER = request.form.getlist('remember')
        print(REMEMBER)
        if not UID_REQUEST or not PWD_REQUEST:
            return render_template(page, error="Invalid credentials")

        try:
            conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER},1433;'
                f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};' 
                f'TrustServerCertificate=yes;'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT userID, password, Scope, username, fullname, email, company FROM Users WHERE username = ?
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
                    if len(REMEMBER) > 0:
                        session.permanent = True

                    log_user_action('login_success')

                    return redirect(url_for("dashboard"))
                
            return render_template(page, error="Invalid credentials")

        except Exception as e:
            log_user_action('login_failed')
            app.logger.error(f"Database error during login: {e}")
            return render_template(page, error="Login temporarily unavailable")
        
    return render_template(page)

@app.route("/logout")
def logout():
    log_user_action('logout')
    session.pop('username', None)
    session.pop('userid', None)
    return redirect(url_for("login", page="index.html"))

@app.route('/forgot_password')
def forgot_password():
    return render_template("forgot_password.html")

@app.route('/set_new_password', methods=['POST', 'GET'])
def set_new_password():
    email_for_password_reset = session['email_for_password_reset']
    new_password = request.form['new-password']
    confirm_password = request.form['confirm-password']

    if new_password != confirm_password:
        return render_template("reset_password.html", error="Passwords do not match")
    if not new_password or not confirm_password:
        return render_template("reset_password.html", error="All Fields must be filled")
    
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
        f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
        f'UID={DB_UID};'
        f'PWD={DB_PWD};'
        f'TrustServerCertificate=yes;'
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    cursor.execute(
        """
            SELECT password FROM Users WHERE Email = ?
        """, email_for_password_reset
    )
    row = cursor.fetchone()
    stored_hash = row[0]

    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')    

    if bcrypt.checkpw(new_password.encode('utf-8'), stored_hash):
        return render_template("reset_password.html", error="New Password musn't be previously used password")

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

    log_user_action('reset_password')
    return render_template("reset_password.html", message="Password changed")

@app.route('/reset_password/<token>')
def reset_password(token):
    try:
        session['email_for_password_reset'] = s.loads(token, salt='password-reset-salt', max_age=900)
        return render_template('reset_password.html')
    except SignatureExpired:
        flash('The password reset link has expired.', 'danger')
        return redirect(url_for('index'))
    except Exception:
        flash('The password reset link is invalid.', 'danger')
        return redirect(url_for('reset_request'))
    
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
                "subject": "Sydoc Portal Password Reset Request",
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
                                                                        Password Reset Request
                                                                    </h1>
                                                                    <p style="margin: 20px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        Hello,
                                                                    </p>
                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        We received a request to reset the password for your account. You can reset your password by clicking the button below.
                                                                    </p>
                                                                    
                                                                    <table border="0" cellspacing="0" cellpadding="0" width="100%" style="margin-top: 30px; margin-bottom: 30px;">
                                                                        <tr>
                                                                            <td align="center">
                                                                                <table border="0" cellspacing="0" cellpadding="0">
                                                                                    <tr>
                                                                                        <td align="center" style="border-radius: 5px; background-color: #3b82f6;">
                                                                                            <a href="{link}" target="_blank" style="font-size: 16px; font-family: Arial, sans-serif; font-weight: bold; color: #ffffff; text-decoration: none; border-radius: 5px; padding: 15px 25px; border: 1px solid #4338ca; display: inline-block;">
                                                                                                Reset Your Password
                                                                                            </a>
                                                                                        </td>
                                                                                    </tr>
                                                                                </table>
                                                                            </td>
                                                                        </tr>
                                                                    </table>

                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        If you did not request a password reset, please ignore this email. This link is valid for 15 minutes.
                                                                    </p>
                                                                    <p style="margin: 15px 0 0 0; font-family: Arial, sans-serif; font-size: 16px; line-height: 24px; color: #555555;">
                                                                        Thanks,<br>The Sydoc Team
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

@app.route('/request-password-reset', methods=['GET', 'POST'])
def request_password_reset():
    request_email = request.form['email']
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
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
            return render_template("forgot_password.html", message="A password reset link has been sent to your email")
        else:
            return render_template('forgot_password.html', error="Unexpected Error occurred")
    return render_template('forgot_password.html', error="Invalid Email Address")

@app.route("/")
def index():
    if 'username' in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

def get_absolute_dashboard_stats():
    stats = {}
    conn = None
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
        cursor.execute(
            """
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
                WHERE p.Name = '02_Posteingang'
                    AND p.ClientName = 'Privera'
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
            WHERE p.Name = '02_Posteingang'
                AND p.ClientName = 'Privera'
                AND a.ActivityInstanceName = 'C+A';
            """
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

def get_dashbord_preview_documents_stats():
    stats = {}
    conn = None
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
        cursor.execute("""
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
            WHERE tp.Name = '02_Posteingang' AND tp.ClientName = 'Privera' AND
            tdi.Name = 'PLATFORM_DocumentType' AND tdi.StringValue = 'Document'
            AND twi.Status <> 2 
        )
        SELECT DISTINCT TOP 10 tdi.StringValue Barcode
        ,Activity FROM CTE
        LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = CTE.WorkItemID 
        WHERE tdi.Name = 'Barcode' and tdi.StringValue is not NULL
        AND CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
            """
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
    if 'username' not in session:
        return redirect(url_for("login", page='index.html'))
    
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')
    userid = session.get('userid', 'Unknown')

    absolute_stats = get_absolute_dashboard_stats()

    log_user_action('visit_dashboard')
    return render_template("dashboard.html", 
    logged_in_user=logged_in_user,
    scope=scope,
    userid=userid,
    ReadyTotal=absolute_stats['ReadyTotal'],
    InProgressTotal=absolute_stats['InProgressTotal'],
    DoneTotal=absolute_stats['DoneTotal'],
    BacklogTotal=absolute_stats['BacklogTotal']
    )

@app.route("/api/dashboard_stats_absolute")
def dashboard_stats_absolute():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    stats = get_absolute_dashboard_stats()
    return jsonify(stats) 

@app.route("/api/dashboard_stats_document_preview")
def dashboard_stats_document_preview():
    if 'username' not in session:
        return jsonify({"error": "Not authorized"}), 401
    stats = get_dashbord_preview_documents_stats()
    return stats

@app.route("/workitems")
def workitems_overview():
    # Check if user is logged in
    if 'username' not in session:
        return redirect(url_for('login', page='index.html'))

    logged_in_user = session.get('username')
    userid = session.get('userid')
    scope = session.get('scope')
    
    # Connect to runtime database to get workitems
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER_PRD},1433;'
        f'DATABASE={DB_SERVER_DB_RUNTIME};'
        f'UID={DB_UID};'
        f'PWD={DB_PWD};'
        f'TrustServerCertificate=yes;'
    )
    
    # Get all workitems
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
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
            WHERE tp.Name = '02_Posteingang' AND tp.ClientName = 'Privera' AND
            tdi.Name = 'PLATFORM_DocumentType' AND tdi.StringValue = 'Document'
            AND twi.Status <> 2 
        )
        SELECT DISTINCT TOP 1000 tdi.StringValue Barcode, CTE.ModifiedAt, CTE.WorkItemID, CTE.Status 
        FROM CTE
        LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = CTE.WorkItemID 
        WHERE tdi.Name = 'Barcode' and tdi.StringValue is not NULL
        AND CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
        """)
        
        workitems = cursor.fetchall()
        
        # Convert to list of dictionaries for easier template handling
        workitems_list = []
        for row in workitems:
            workitems_list.append({
                'barcode': row[0],                    
                'modifiedat': row[1],           
                'workitemid' : row[2],
                'status': row[3]        
            })
            
    except Exception as e:
        app.logger.error(f"Database error in workitems overview: {e}")
        workitems_list = []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

    log_user_action('visit_workitemList')
    return render_template("workitems_overview.html", 
                         logged_in_user=logged_in_user,
                         userid=userid,
                         scope=scope,
                         workitems=workitems_list)
    
@app.route("/demand_workitem", methods=['POST', 'GET'])
def demand_workitem():
    if 'username' not in session:
        return redirect(url_for("login", page='index.html'))
    if request.method == "POST":
        workitemid = request.form['workitemid']
        log_user_action('demand_workitem', resource_id=workitemid)
        username = session['username']

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER},1433;'
            f'DATABASE={DB_SERVER_DB_STAT};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        print(workitemid)
        cursor.execute("""
            UPDATE StadtBiel
            SET DemandedBy = ?, [DateTime] = GETDATE()
            WHERE FileID = ?
        """, (username, workitemid))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect(url_for("workitems_overview"))       

@app.route("/profile")
def profile():
    if 'username' not in session:
        return redirect(url_for("login", page='index.html'))
    
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')
    userid = session.get('userid', 'Unknown')
    fullname = session.get('fullname', 'Unknown')
    email = session.get('email', 'Unknown')
    company = session.get('company', 'Unknown')
    log_user_action('visit_profile')
    return render_template("profile.html", userid=userid, logged_in_user=logged_in_user, scope=scope, fullname=fullname, email=email, company=company)
  
@app.route("/update_profile", methods=["POST", "GET"])
def update_profile():
    if 'username' not in session:
        return redirect(url_for("login", page='index.html'))
    if request.method == "POST":
        userid = session['userid']
        username = session['username']
        fullname = request.form['fullName']
        email = request.form['email']
        company = request.form['company']

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER},1433;'
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

        if request.files['file']:
            f = request.files['file']
            filename = f"{userid}-icon.png"
            rel_path = os.path.join('static', 'images', filename)
            abs_path = os.path.join(app.root_path, rel_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
            f.save(abs_path)

        log_user_action('update_profile_info', details={
            "fullname": fullname,
            "email": email,
            "company": company
        })
        return redirect(url_for("profile"))

@app.route('/change_password',  methods=["POST", "GET"]) 
def change_password():
    if 'username' not in session:
        return redirect(url_for("login", page='index.html'))
    
    if request.method == "POST":
        username = session['username']

        currentPassword = request.form['currentPassword'] 
        newPassword = request.form['newPassword']
        confirmPassword = request.form['confirmPassword']

        if newPassword != confirmPassword:
            return render_template("profile.html", error="Passwords do not match")
        if not newPassword or not confirmPassword or not currentPassword:
            return render_template("profile.html", error="All Fields must be filled")

        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER},1433;'
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

            log_user_action('change_password')
            return render_template("profile.html", message="Password changed")
        else:
            return render_template("profile.html", error="Invalid Password")

@app.route('/api/recent_activity')
def recent_activity():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401

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
        cursor.execute("""
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
            WHERE tp.Name = '02_Posteingang' AND tp.ClientName = 'Privera' AND
            tdi.Name = 'PLATFORM_DocumentType' AND tdi.StringValue = 'Document'
            AND twi.Status <> 2 
        )
        SELECT DISTINCT TOP 4 tdi.StringValue Barcode, CTE.Status, CTE.ModifiedAt FROM CTE
        LEFT JOIN t_DocumentIndexes tdi ON tdi.WorkItemID = CTE.WorkItemID 
        WHERE tdi.Name = 'Barcode' and tdi.StringValue is not NULL
        AND CAST(CTE.ModifiedAt AS DATE) = CAST(GETDATE() AS DATE)
        """)
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

@app.route('/allstatesfromoneworkitem/<string:workitem_id>')
def all_states_from_one_workitem(workitem_id):
    #if 'username' not in session:
    #    return jsonify({"error": "Not logged in"}), 401

    try:
        conn_str = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={DB_SERVER},1433;'
            f'DATABASE={DB_SERVER_DB_STAT};'
            f'UID={DB_UID};'
            f'PWD={DB_PWD};'
            f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM 
            dbo.StadtBiel 
            WHERE FileID = ?;
        """, (workitem_id,))
        all_states_from_one_workitem = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([
            {
                "state": row[4],
                "DemandedBy": row[5],
                "datetime": row[6] if isinstance(row[6], str) else row[6].strftime('%Y-%m-%d %H:%M:%S')
            }
            for row in all_states_from_one_workitem
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/jdvance')
def jdvance():
    if 'username' in session and session['scope'] == 'Admin':
        return render_template("jdvance.html")
    else:
        return render_template("404.html"), 404

@app.route('/language/<lang>')
def set_language(lang=None):
    session['locale'] = lang
    log_user_action('change_language', details={"new_language": lang})
    return redirect(request.referrer or url_for('index'))

@app.context_processor
def inject_current_lang():
    current_lang = session.get('locale', 'en')
    return {'current_lang': current_lang}

@app.route("/log_action", methods=['POST'])
def log_action():
    if 'username' not in session:
        return jsonify({'error': 'not authenticated'}), 401
    
    data = request.get_json()
    log_user_action(data.get('action_type'),
                    data.get('resource_id'),
                    data.get('details'))
    
    return jsonify({'success': True})

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(DatabaseError)
def special_exception_handler():
    return 'Database connection failed', 500

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

def get_extension_and_urls(workitemdata, document_id):
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
    for element in response.json()['Media']:
        if str(element['Extension']).lower() in ('.jpg', '.jpeg', '.png', '.tif'):
            urls.append(element['Url'])
            extension.append(element['Extension'])
    return extension, urls

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
            return jsonify({"error": "Workitem not found"}), 404

        workitemdata, document_id = returndata
        extensions, urls = get_extension_and_urls(workitemdata, document_id)
        
        media_count = len(urls) if urls else 0
        
        if media_count > 0:
            cache.set(f"media_data_{workitem_id}", {'extensions': extensions, 'urls': urls})

        response_data = {
            "workitem_id": workitem_id,
            "media_count": media_count
        }
        
        cache.set(f"media_info_{workitem_id}", response_data)

        return jsonify(response_data)
    except Exception as e:
        print(f"An error occurred in get_media_info: {e}")
        return jsonify({"error": "Internal Server Error"}), 500
    
@app.route('/api/get_media_raw/<int:workitem_id>/<int:media_index>')
def api_get_media_raw(workitem_id, media_index):
    try:
        media_data = cache.get(f"media_data_{workitem_id}")
        if not media_data:
            returndata = get_workitemdata_param(workitem_id)
            if not returndata:
                return Response("Workitem not found", status=404)

            workitemdata, document_id = returndata
            extensions, urls = get_extension_and_urls(workitemdata, document_id)
            media_data = {'extensions': extensions, 'urls': urls}
            cache.set(f"media_data_{workitem_id}", media_data)
        
        extensions = media_data.get('extensions', [])
        urls = media_data.get('urls', [])

        if media_index >= len(urls):
            return Response("Media index out of bounds", status=404)

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
                return "Failed to process TIFF image", 500
            
        response = make_response(raw_media_bytes)
        response.headers.set('Content-Type', mimetype)
        
        response.headers.set(
            'Cache-Control', 'public, max-age=3600'
        )
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        return Response("Internal Server Error", status=500)

# ------------------------------- ONLY FOR IIS ------------------------------- #c   
#  app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/sydocportal')
# ------------------------------------- - ------------------------------------ #

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)