-- 0006_create_reporting_sql_tables.sql
-- Phase 2 live-SQL sandbox: audit log of every execution, and a per-user
-- one-time acknowledgment of the SQL notice. Idempotent.
IF OBJECT_ID(N'dbo.ReportingSqlAudit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingSqlAudit (
        Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingSqlAudit PRIMARY KEY,
        UserID        INT NULL,
        Username      NVARCHAR(100) NULL,
        TargetDB      NVARCHAR(50) NOT NULL,
        SqlText       NVARCHAR(MAX) NOT NULL,
        RowsReturned  INT NULL,
        Status        NVARCHAR(16) NOT NULL,   -- run | rejected | error
        DurationMs    INT NULL,
        CreatedAt     DATETIME2 NOT NULL
                      CONSTRAINT DF_ReportingSqlAudit_CreatedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ReportingSqlAudit_User ON dbo.ReportingSqlAudit(UserID, CreatedAt);
END;
GO

IF OBJECT_ID(N'dbo.ReportingSqlAck', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingSqlAck (
        UserID      INT NOT NULL CONSTRAINT PK_ReportingSqlAck PRIMARY KEY,
        AcceptedAt  DATETIME2 NOT NULL
                    CONSTRAINT DF_ReportingSqlAck_AcceptedAt DEFAULT SYSUTCDATETIME()
    );
END;
GO
