from fileinput import filename
from flask import Flask, render_template, request, redirect, url_for, session
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

app = Flask(__name__)
load_dotenv()

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True  
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  

DB_UID = os.environ.get("DB_UID")
DB_PWD = os.environ.get("DB_PWD")
DB_SERVER = os.environ.get("DB_SERVER")
DB_SERVER_DB_WEBPORTAL = os.environ.get("DB_SERVER_DB_WEBPORTAL")
DB_SERVER_DB_STAT = os.environ.get("DB_SERVER_DB_STAT")
DB_SERVER_DB_RUNTIME = os.environ.get("DB_SERVER_DB_RUNTIME")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        UID_REQUEST = request.form["username"]
        PWD_REQUEST = request.form["password"]
        
        if not UID_REQUEST or not PWD_REQUEST:
            return render_template("index.html", error="Invalid credentials")
        
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
                SELECT password, Scope, username, fullname, email, company FROM Users WHERE username = ?
            """, (UID_REQUEST,))
            user_record = cursor.fetchone()

            if user_record:
                stored_hash = user_record[0]
                scope = user_record[1]
                stored_username = user_record[2]
                stored_fullname = user_record[3]
                stored_email = user_record[4]
                stored_company = user_record[5]
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')    
            
                if bcrypt.checkpw(PWD_REQUEST.encode('utf-8'), stored_hash):
                    session.clear()  
                    session['username'] = stored_username
                    session['fullname'] = stored_fullname
                    session['email'] = stored_email
                    session['scope'] = scope
                    session['company'] = stored_company
                    session.permanent = True
                    return redirect(url_for("post_login"))
                
            return render_template("index.html", error="Invalid credentials")
                
        except Exception as e:
            app.logger.error(f"Database error during login: {e}")
            return render_template("index.html", error="Login temporarily unavailable")
        
    return render_template("index.html")

@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for("login"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/post_login")
def post_login():
    #Check if user is logged in
    if 'username' not in session:
        return redirect(url_for("login"))
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')

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
    cursor.execute(
        """
        SELECT COUNT(*) Count FROM v_StadtBiel_LatestState
        GROUP BY STATE
        ORDER BY State        
        """
    )
    rows = cursor.fetchall()
    DoneTotal = rows[0][0]
    CollectedTotal = rows[1][0]
    InProgressTotal = rows[2][0]
    ReadyTotal = rows[3][0]
    cursor.close()
    conn.close()

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
        WITH TopFieldIds AS (
            SELECT TOP 2
                FileID
            FROM StadtBiel
            GROUP BY FileID
            ORDER BY MAX([DateTime]) DESC
        ),
        AuditStates AS (
            SELECT
                FileID,
                State DisplayState
            FROM StadtBiel
            WHERE FileID IN (SELECT FileID FROM TopFieldIds)
        )
        SELECT
            FileID,
            MAX(CASE WHEN DisplayState = 'Ready' THEN 'True' ELSE 'False' END) AS Ready,
            MAX(CASE WHEN DisplayState = 'In Progress' THEN 'True' ELSE 'False' END) AS [InProgress],
            MAX(CASE WHEN DisplayState = 'Done' THEN 'True' ELSE 'False' END) AS [Done],
            MAX(CASE WHEN DisplayState = 'Collected' THEN 'True' ELSE 'False' END) AS [Collected]
        FROM AuditStates
        GROUP BY FileID
        ORDER BY FileID
        """
    )
    rows = cursor.fetchall()
    FileID = rows[0][0]
    Ready = rows[0][1]
    InProgress = rows[0][2]
    Done = rows[0][3]
    Collected = rows[0][4]

    FileID_ = rows[1][0]
    Ready_ = rows[1][1]
    InProgress_ = rows[1][2]
    Done_ = rows[1][3]
    Collected_ = rows[1][4]
    cursor.close()
    conn.close()

    return render_template("post_login.html", 
    logged_in_user=logged_in_user,
    InProgressTotal=InProgressTotal,
    ReadyTotal=ReadyTotal,
    DoneTotal=DoneTotal,
    CollectedTotal=CollectedTotal,
    scope=scope,
    FileID=FileID, Ready=Ready, InProgress=InProgress, Done=Done, Collected=Collected,
    FileID_=FileID_, Ready_=Ready_, InProgress_=InProgress_, Done_=Done_, Collected_=Collected_
    )

@app.route("/workitems")
def workitems_overview():
    # Check if user is logged in
    if 'username' not in session:
        return redirect(url_for('login'))
    
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')
    
    # Connect to runtime database to get workitems
    conn_str = (
        f'DRIVER={{SQL Server}};'
        f'SERVER={DB_SERVER},1433;'
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
            SELECT 
                ID as WorkitemID,
                DateCreated,
                Priority,
                CASE
                    WHEN Priority = 50 THEN 'Normal'
                    WHEN Priority > 100 THEN 'High'
                    WHEN Priority < 50 THEN 'Low'
                    ELSE 'Unknown'
                END as PriorityText,
                Status,
                CASE 
                    WHEN Status = 0 THEN 'Ready'
                    WHEN Status = 1 THEN 'In Progress'
                    WHEN Status = 2 THEN 'Undefined'
                    WHEN Status = 3 THEN 'Error'
                    WHEN Status = 4 THEN 'Reserved'
                    WHEN Status = 5 THEN 'Done'
                    ELSE 'Unknown'
                END as StatusText
            FROM t_WorkItems
            ORDER BY DateCreated DESC
        """)
        
        workitems = cursor.fetchall()
        
        # Convert to list of dictionaries for easier template handling
        workitems_list = []
        for row in workitems:
            workitems_list.append({
                'id': row[0],                    # ID
                'created_on': row[1],            # DateCreated
                'priority': row[2],              # Priority
                'priority_text': row[3],         # PriorityText
                'status': row[4],                # Status
                'status_text': row[5]            # StatusText
            })
            
    except Exception as e:
        app.logger.error(f"Database error in workitems overview: {e}")
        workitems_list = []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    
    return render_template("workitems_overview.html", 
                         logged_in_user=logged_in_user,
                         scope=scope,
                         workitems=workitems_list)
    
@app.route("/profile")
def profile():
    if 'username' not in session:
        return redirect(url_for("login"))
    
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')
    fullname = session.get('fullname', 'Unknown')
    email = session.get('email', 'Unknown')
    company = session.get('company', 'Unknown')
    return render_template("profile.html", logged_in_user=logged_in_user, scope=scope, fullname=fullname, email=email, company=company)

@app.route("/update_profile", methods=["POST", "GET"])
def update_profile():
    if 'username' not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        scope = session['scope']
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
            filename = f"{scope}-icon.png"
            rel_path = os.path.join('static', 'images', filename)
            abs_path = os.path.join(app.root_path, rel_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
            f.save(abs_path)

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

            return render_template("profile.html", message="Password changed")
        else:
            return render_template("profile.html", error="Invalid Password")

@app.route('/change_language',  methods=["POST", "GET"]) 
def change_language():
    if 'username' not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        username = session['username']
        currentLanguage = request.form['currentLanguage']
        print(currentLanguage)
        return redirect(url_for("profile"))

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(DatabaseError)
def special_exception_handler():
    return 'Database connection failed', 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)