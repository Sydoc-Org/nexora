from flask import Flask, render_template, request, redirect, url_for, session
import pyodbc
from dotenv import load_dotenv
import os
from datetime import timedelta
import bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
load_dotenv()

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=1)
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
                f'DRIVER={{ODBC Driver 17 for SQL Server}};'
                f'SERVER={DB_SERVER},1433;'
                f'DATABASE={DB_SERVER_DB_WEBPORTAL};'
                f'UID={DB_UID};'
                f'PWD={DB_PWD};' 
                f'TrustServerCertificate=yes;'
            )
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT password, Scope FROM Users WHERE username = ?
            """, (UID_REQUEST,))
            user_record = cursor.fetchone()

            if user_record:
                stored_hash = user_record[0]
                scope = user_record[1]
                if isinstance(stored_hash, str):
                    stored_hash = stored_hash.encode('utf-8')    
            
                if bcrypt.checkpw(PWD_REQUEST.encode('utf-8'), stored_hash):
                    session.clear()  
                    session['username'] = UID_REQUEST
                    session['scope'] = scope
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
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
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
    Done = rows[0][0]
    Exported = rows[1][0]
    InProgress = rows[2][0]
    Pending = rows[3][0]
    cursor.close()
    conn.close()

    # conn_str = (
    #     f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    #     f'SERVER={DB_SERVER},1433;'
    #     f'DATABASE={DB_SERVER_DB_STAT};'
    #     f'UID={DB_UID};'
    #     f'PWD={DB_PWD};'
    #     f'TrustServerCertificate=yes;'
    # )
    # conn = pyodbc.connect(conn_str)
    # cursor = conn.cursor()
    # cursor.execute("""
    #     SET NOCOUNT ON;
    #     DECLARE @table table (Scope NVARCHAR(50), Import int, Export int, ExportThisMonth int);

    #     INSERT INTO @table
    #     SELECT 'ElektroMaterial' Scope, (
    #     select COUNT(*) from EM_Invoice
    #     where CAST(ImportDatetime AS DATE) = CAST(GETDATE() AS DATE)
    #     ),
    #     (SELECT 
    #         COUNT(*)
    #     FROM 
    #         EM_Invoice
    #     WHERE 
    #         TRY_CONVERT(DATE, ExportEM, 104) = cast(getdate() as date)
    #     ),
    #     (SELECT 
    #         COUNT(*)
    #     FROM 
    #         EM_Invoice
    #     WHERE 
    #         MONTH(TRY_CONVERT(DATE, ExportEM, 104)) = MONTH(GETDATE())
    #         and YEAR(TRY_CONVERT(DATE, ExportEM, 104)) = YEAR(GETDATE())
    #     )

    #     UNION ALL

    #     SELECT 'Privera', (
    #     select COUNT(*) from PriveraInvoice
    #     where CAST(ImportTime AS DATE) = CAST(GETDATE() AS DATE)
    #     ) + (
    #     select COUNT(*) from PriveraPosteingang
    #     where CONVERT(DATE, ImportDatetime, 104) = CAST(GETDATE() AS DATE)
    #     ),
    #     (SELECT 
    #         COUNT(*)
    #     FROM 
    #         PriveraInvoice
    #     WHERE 
    #         CAST(ExportDate AS DATE) = cast(getdate() as date)
    #     ) + (SELECT 
    #         COUNT(*)
    #     FROM 
    #         PriveraPosteingang
    #     WHERE 
    #         CONVERT(DATE, ExportDatetime, 104) = cast(getdate() as date)
    #     ),
    #     (SELECT 
    #         COUNT(*)
    #     FROM 
    #         PriveraInvoice
    #     WHERE 
    #         MONTH(ExportDate) = MONTH(GETDATE()) AND YEAR(ExportDate) = YEAR(GETDATE())
    #     ) + (SELECT 
    #         COUNT(*)
    #     FROM 
    #         PriveraPosteingang
    #     WHERE 
    #         MONTH(CONVERT(DATE, ExportDatetime, 104)) = MONTH(GETDATE()) AND YEAR(CONVERT(DATE, ExportDatetime, 104)) = YEAR(GETDATE())
    #     )
    #     SELECT * FROM @table
    #     WHERE Scope = ?
    #     """, scope
    # )
    # rows = cursor.fetchone()
    # Import = rows[1]
    # Export = rows[2]
    # ExportThisMonth = rows[3]
    # cursor.close()
    # conn.close()

    workitem = 487396
    InOCR = 'True'
    InCA = 'False'
    InExport = 'False'
    DateTime = '2025-07-30 08:30'

    return render_template("post_login.html", 
    logged_in_user=logged_in_user,
    InProgress=InProgress,
    Pending=Pending,
    Done=Done,
    Exported=Exported,
    scope=scope,
    workitem=workitem, InOCR=InOCR, InCA=InCA, InExport=InExport, DateTime=DateTime
    )
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)