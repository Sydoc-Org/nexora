@app.route("/post_login")
def post_login():
    logged_in_user = session.get('username', 'Unknown')
    scope = session.get('scope', 'Unknown')

    conn_str = (
        f'DRIVER={{ODBC Driver 17 for SQL Server}};'
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
            select COUNT(*) WorkitemsInProgress
            from t_WorkItems workitems
            LEFT JOIN t_ActivityInstances activites on activites.ID = workitems.ActivityInstanceID
            LEFT JOIN t_Processes processes on processes.ID = activites.ProcessID
            WHERE workitems.[Status] not in (5,2) AND activites.ActivityInstanceName not like '%Pause Process%'
            and processes.ClientName = ? 
        """, scope
    )
    rows = cursor.fetchone()
    WorkitemsInProgress = rows[0]
    cursor.close()
    conn.close()

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
    cursor.execute("""
        SET NOCOUNT ON;
        DECLARE @table table (Scope NVARCHAR(50), Import int, Export int, ExportThisMonth int);

        INSERT INTO @table
        SELECT 'ElektroMaterial' Scope, (
        select COUNT(*) from EM_Invoice
        where CAST(ImportDatetime AS DATE) = CAST(GETDATE() AS DATE)
        ),
        (SELECT 
            COUNT(*)
        FROM 
            EM_Invoice
        WHERE 
            TRY_CONVERT(DATE, ExportEM, 104) = cast(getdate() as date)
        ),
        (SELECT 
            COUNT(*)
        FROM 
            EM_Invoice
        WHERE 
            MONTH(TRY_CONVERT(DATE, ExportEM, 104)) = MONTH(GETDATE())
            and YEAR(TRY_CONVERT(DATE, ExportEM, 104)) = YEAR(GETDATE())
        )

        UNION ALL

        SELECT 'Privera', (
        select COUNT(*) from PriveraInvoice
        where CAST(ImportTime AS DATE) = CAST(GETDATE() AS DATE)
        ) + (
        select COUNT(*) from PriveraPosteingang
        where CONVERT(DATE, ImportDatetime, 104) = CAST(GETDATE() AS DATE)
        ),
        (SELECT 
            COUNT(*)
        FROM 
            PriveraInvoice
        WHERE 
            CAST(ExportDate AS DATE) = cast(getdate() as date)
        ) + (SELECT 
            COUNT(*)
        FROM 
            PriveraPosteingang
        WHERE 
            CONVERT(DATE, ExportDatetime, 104) = cast(getdate() as date)
        ),
        (SELECT 
            COUNT(*)
        FROM 
            PriveraInvoice
        WHERE 
            MONTH(ExportDate) = MONTH(GETDATE()) AND YEAR(ExportDate) = YEAR(GETDATE())
        ) + (SELECT 
            COUNT(*)
        FROM 
            PriveraPosteingang
        WHERE 
            MONTH(CONVERT(DATE, ExportDatetime, 104)) = MONTH(GETDATE()) AND YEAR(CONVERT(DATE, ExportDatetime, 104)) = YEAR(GETDATE())
        )
        SELECT * FROM @table
        WHERE Scope = ?
        """, scope
    )
    rows = cursor.fetchone()
    Import = rows[1]
    Export = rows[2]
    ExportThisMonth = rows[3]
    cursor.close()
    conn.close()

    workitem = 487396
    InOCR = 'True'
    InCA = 'False'
    InExport = 'False'
    DateTime = '2025-07-30 08:30'

    return render_template("post_login.html", 
    logged_in_user=logged_in_user, InProgress=WorkitemsInProgress,
    Import=Import, Export=Export, ExportThisMonth=ExportThisMonth,
    scope=scope,
    workitem=workitem, InOCR=InOCR, InCA=InCA, InExport=InExport, DateTime=DateTime)
