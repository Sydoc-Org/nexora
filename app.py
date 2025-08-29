from fileinput import filename
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
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
from flask import jsonify
import json
import requests
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

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
    if user is not None and user.locale in ['en', 'de', 'fr']:
        return user.locale
    return request.accept_languages.best_match(['de', 'fr', 'en'])

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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True  
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  

DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER = os.environ.get("DB_SERVER")
DB_SERVER_DB_WEBPORTAL = os.environ.get("DB_SERVER_DB_WEBPORTAL")
DB_SERVER_DB_STAT = os.environ.get("DB_SERVER_DB_STAT")
DB_SERVER_DB_RUNTIME = os.environ.get("DB_SERVER_DB_RUNTIME")
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
GRAPH_USERNAME = os.environ.get("GRAPH_USERNAME")
GRAPH_PASSWORD = os.environ.get("GRAPH_PASSWORD")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

@app.route("/signin")
def signin():
    return render_template("seperate_page_login.html")

@app.route("/login/<page>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login(page=None):
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        
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
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    #Check if user is logged in
    if 'username' not in session:
        return redirect(url_for("login"))
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')
    userid = session.get('userid', 'Unknown')

    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
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
    ReadyTotal = rows[0][0]
    InProgressTotal = rows[1][0]
    DoneTotal = rows[2][0]
    BacklogTotal = rows[3][0]
    cursor.close()
    conn.close()

    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
        f'DATABASE={DB_SERVER_DB_RUNTIME};'
        f'UID={DB_UID};'
        f'PWD={DB_PWD};'
        f'TrustServerCertificate=yes;'
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT top 3
            d.Stringvalue Barcode,
            CASE
                WHEN a.ActivityInstanceName like '%C+A%' THEN
                    'InValidation'
                WHEN a.ActivityInstanceName like '%Export%'
                    OR a.ActivityInstanceName like '%Exp%' THEN
                    'InExport'
                WHEN a.ActivityInstanceName like '%Import%'
                    OR a.ActivityInstanceName like '%Imp%' THEN
                    'InImport'
                WHEN a.ActivityInstanceName like '%Extract%' THEN
                    'InExtraction'
                WHEN a.ActivityInstanceName like '%OCR%' THEN
                    'InOCR'
                WHEN a.ActivityInstanceName like '%Statistik%' THEN
                    'InDBSaving'
                WHEN a.ActivityInstanceName like '%Collect%' THEN
                    'InDBSaving'
                ELSE
                    'InValidation'
            END AS Activity
        FROM t_WorkItems w
            LEFT JOIN t_ActivityInstances a
                on a.id = w.ActivityInstanceID
            LEFT JOIN t_Processes p
                on p.id = a.ProcessID
            LEFT JOIN t_DocumentIndexes d
                on w.ID = d.WorkItemID
        WHERE CAST(w.DateCreated AS DATE) = CAST(GETDATE() AS DATE)
            and d.Name = 'Barcode'
            AND p.Name = '02_Posteingang'
            AND p.ClientName = 'Privera'
        ORDER by newid()
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    log_user_action('visit_dashboard')
    return render_template("dashboard.html", 
    logged_in_user=logged_in_user,
    InProgressTotal=InProgressTotal,
    ReadyTotal=ReadyTotal,
    DoneTotal=DoneTotal,
    BacklogTotal=BacklogTotal,
    scope=scope, userid=userid,
    rows=rows
    )

@app.route("/workitems")
def workitems_overview():
    # Check if user is logged in
    if 'username' not in session:
        return redirect(url_for('login'))

    logged_in_user = session.get('username')
    userid = session.get('userid')
    scope = session.get('scope')
    
    # Connect to runtime database to get workitems
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
        f'DATABASE={DB_SERVER_DB_STAT};'
        f'UID={DB_UID};'
        f'PWD={DB_PWD};'
        f'TrustServerCertificate=yes;'
    )
    
    # Get all workitems
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                wi.FileID as WorkitemID,
                ( 
                    SELECT TOP 1 DateTime 
                    FROM StadtBiel sb 
                    WHERE sb.FileID = wi.FileID AND sb.State = 'Ready'
                    ORDER BY DateTime DESC
                ) as DateCreated,
                (  
                    SELECT TOP 1 
                        CASE 
                            WHEN DemandedBy IS NULL THEN 'False'
                            ELSE 'True'
                        END
                    FROM StadtBiel sb 
                    WHERE sb.FileID = wi.FileID
                    ORDER BY DateTime DESC
                ) as Demanded,
                wi.State as StatusText
            FROM v_StadtBiel_LatestState wi
            GROUP BY wi.FileID, wi.State
            ORDER BY wi.FileID ASC
        """)
        
        workitems = cursor.fetchall()
        
        # Convert to list of dictionaries for easier template handling
        workitems_list = []
        for row in workitems:
            workitems_list.append({
                'id': row[0],                    
                'created_on': row[1],            
                'demanded': row[2],              
                'status_text': row[3],           
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
        return redirect(url_for("login"))
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
        return redirect(url_for("login"))
    
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
        return redirect(url_for("login"))
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
        return redirect(url_for("login"))
    
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

@app.route('/recent_activity')
def recent_activity():
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401

    try:
        conn_str = (
                f'DRIVER={{SQL Server}};'
                f'SERVER={DB_SERVER},1433;'
                f'DATABASE={DB_SERVER_DB_RUNTIME};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};'
                f'TrustServerCertificate=yes;'
        )
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT TOP 4
                CASE
                    WHEN w.[Status] = 0 THEN
                        'Ready'
                    WHEN w.[Status] = 1 THEN
                        'In Progress'
                    WHEN w.[Status] = 5 THEN
                        'Done'
                    ELSE
                        'Ready'
                end as state,
                DATEADD(HOUR, 2, wa.[TimeStamp]) datetime,
                d.StringValue fileid
            FROM t_WorkItems w
                LEFT JOIN t_WorkItemAudits wa
                    ON w.ID = wa.WorkItemID
                LEFT JOIN t_ActivityInstances a
                    ON a.id = w.ActivityInstanceID
                LEFT JOIN t_DocumentIndexes d
                    ON d.WorkItemID = w.id
                LEFT JOIN t_Processes p
                    ON p.id = a.ProcessID
            WHERE p.ClientName = 'Privera'
                AND p.Name = '02_Posteingang'
                AND w.LastAuditNumber = wa.AuditNumber
                AND d.Name = 'Barcode'
            ORDER BY DATEADD(HOUR, 2, wa.[TimeStamp]) desc
        """)
        activities = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([
            {
                "state": row[0],
                "datetime": row[1].strftime('%Y-%m-%d %H:%M:%S'),  
                "Barcode": row[2]
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
    return render_template("jdvance.html")

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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)