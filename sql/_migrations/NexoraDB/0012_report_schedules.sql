-- 0012_report_schedules.sql
-- Scheduled report delivery: a saved report can be run on a recurring schedule
-- and emailed (xlsx/csv) to recipients by the ops/run_scheduled_reports.py runner
-- (driven by Windows Task Scheduler). Gated by a new grantable reporting.schedule
-- permission. Idempotent.

IF OBJECT_ID(N'dbo.ReportSchedules', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportSchedules (
        ScheduleID   INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportSchedules PRIMARY KEY,
        ReportID     INT NOT NULL,
        OwnerUserID  INT NOT NULL,
        Recipients   NVARCHAR(1000) NOT NULL,        -- comma/semicolon-separated emails
        Format       NVARCHAR(8) NOT NULL CONSTRAINT DF_ReportSchedules_Format DEFAULT 'xlsx',
        Frequency    NVARCHAR(10) NOT NULL,           -- daily | weekly | monthly
        Hour         TINYINT NOT NULL CONSTRAINT DF_ReportSchedules_Hour DEFAULT 6,
        Minute       TINYINT NOT NULL CONSTRAINT DF_ReportSchedules_Minute DEFAULT 0,
        Weekday      TINYINT NULL,                    -- 0=Mon..6=Sun (weekly)
        DayOfMonth   TINYINT NULL,                    -- 1..28 (monthly)
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportSchedules_Enabled DEFAULT 1,
        LastRunAt    DATETIME2 NULL,
        NextRunAt    DATETIME2 NULL,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportSchedules_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportSchedules_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ReportSchedules_Reports FOREIGN KEY (ReportID)
            REFERENCES dbo.Reports(ReportID) ON DELETE CASCADE,
        CONSTRAINT FK_ReportSchedules_Users FOREIGN KEY (OwnerUserID)
            REFERENCES dbo.Users(userID),
        CONSTRAINT CK_ReportSchedules_Format CHECK (Format IN ('xlsx', 'csv')),
        CONSTRAINT CK_ReportSchedules_Frequency CHECK (Frequency IN ('daily', 'weekly', 'monthly'))
    );
    CREATE INDEX IX_ReportSchedules_Due ON dbo.ReportSchedules(Enabled, NextRunAt);
END;
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.schedule', 'Reporting: schedule a report to run and be emailed'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.schedule');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.schedule'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
