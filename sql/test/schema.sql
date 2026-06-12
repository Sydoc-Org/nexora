-- NEXORA_TEST schema. Idempotent — safe to run repeatedly.
-- Subset of nexora that round-1 tests need (auth + permissions + sessions).
-- NO `USE` statement: sqlcmd -d NEXORA_TEST in scripts/test-db-reset.ps1 sets the database.
-- Schema mirrors sql/NexoraDB/Tables/*.sql but without the nexora-specific FK constraint names.

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- Drop dependent procs/funcs first
IF OBJECT_ID('dbo.spGetUserPermissions', 'P') IS NOT NULL DROP PROCEDURE dbo.spGetUserPermissions;
GO
IF OBJECT_ID('dbo.fnUserHasPermission', 'FN') IS NOT NULL DROP FUNCTION dbo.fnUserHasPermission;
GO

-- Drop tables in FK-safe order (children first).
-- Reporting tables are dropped here too: dbo.Reports has an FK to dbo.Users, so
-- it must go before Users or the reset fails on re-run (they are recreated near
-- the bottom of this file). ReportingSqlAudit/Ack have no FK but are dropped for
-- a clean, fully idempotent reset.
IF OBJECT_ID('dbo.ReportSchedules', 'U') IS NOT NULL DROP TABLE dbo.ReportSchedules;
IF OBJECT_ID('dbo.ReportingMetrics', 'U') IS NOT NULL DROP TABLE dbo.ReportingMetrics;
IF OBJECT_ID('dbo.ReportingSources', 'U') IS NOT NULL DROP TABLE dbo.ReportingSources;
IF OBJECT_ID('dbo.ReportShares', 'U') IS NOT NULL DROP TABLE dbo.ReportShares;
IF OBJECT_ID('dbo.Reports', 'U') IS NOT NULL DROP TABLE dbo.Reports;
IF OBJECT_ID('dbo.ReportingSqlAudit', 'U') IS NOT NULL DROP TABLE dbo.ReportingSqlAudit;
IF OBJECT_ID('dbo.ReportingSqlAck', 'U') IS NOT NULL DROP TABLE dbo.ReportingSqlAck;
IF OBJECT_ID('dbo.UserPermissionOverride', 'U') IS NOT NULL DROP TABLE dbo.UserPermissionOverride;
IF OBJECT_ID('dbo.AccessProfilePermission', 'U') IS NOT NULL DROP TABLE dbo.AccessProfilePermission;
IF OBJECT_ID('dbo.ActiveSessions', 'U') IS NOT NULL DROP TABLE dbo.ActiveSessions;
IF OBJECT_ID('dbo.Users', 'U') IS NOT NULL DROP TABLE dbo.Users;
IF OBJECT_ID('dbo.Permission', 'U') IS NOT NULL DROP TABLE dbo.Permission;
IF OBJECT_ID('dbo.AccessProfile', 'U') IS NOT NULL DROP TABLE dbo.AccessProfile;
IF OBJECT_ID('dbo.Organizations', 'U') IS NOT NULL DROP TABLE dbo.Organizations;
GO

-- Organizations (parent of Users)
CREATE TABLE dbo.Organizations (
    organizationcode NVARCHAR(5) NOT NULL PRIMARY KEY,
    Organization NVARCHAR(200) NULL
);
GO

-- AccessProfile (parent of Users via accessid)
CREATE TABLE dbo.AccessProfile (
    AccessID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Name NVARCHAR(50) NOT NULL UNIQUE,
    Description NVARCHAR(200) NULL
);
GO

-- Permission
CREATE TABLE dbo.Permission (
    PermissionID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Code SYSNAME NOT NULL UNIQUE,
    Description NVARCHAR(200) NOT NULL
);
GO

-- Users
CREATE TABLE dbo.Users (
    userID INT IDENTITY(1001,1) NOT NULL PRIMARY KEY,
    username NVARCHAR(50) NULL UNIQUE,
    password NVARCHAR(255) NULL,
    Fullname NVARCHAR(255) NULL,
    Email NVARCHAR(255) NULL UNIQUE,
    accessid INT NULL FOREIGN KEY REFERENCES dbo.AccessProfile(AccessID),
    organizationCode NVARCHAR(5) NULL FOREIGN KEY REFERENCES dbo.Organizations(organizationcode),
    InitReset BIT NULL,
    twoFA BIT NULL,
    twoFASecret NVARCHAR(100) NULL,
    locale NVARCHAR(3) NULL
);
GO

-- AccessProfilePermission (M:N between AccessProfile and Permission)
CREATE TABLE dbo.AccessProfilePermission (
    AccessID INT NOT NULL FOREIGN KEY REFERENCES dbo.AccessProfile(AccessID),
    PermissionID INT NOT NULL FOREIGN KEY REFERENCES dbo.Permission(PermissionID),
    Effect CHAR(1) NOT NULL CHECK (Effect IN ('A', 'D')),
    PRIMARY KEY (AccessID, PermissionID)
);
GO

-- UserPermissionOverride (per-user grants/denies, takes precedence over access profile)
CREATE TABLE dbo.UserPermissionOverride (
    UserID INT NOT NULL FOREIGN KEY REFERENCES dbo.Users(userID),
    PermissionID INT NOT NULL FOREIGN KEY REFERENCES dbo.Permission(PermissionID),
    Effect CHAR(1) NOT NULL CHECK (Effect IN ('A', 'D')),
    PRIMARY KEY (UserID, PermissionID)
);
GO

-- ActiveSessions (login flow inserts here via _record_active_session)
CREATE TABLE dbo.ActiveSessions (
    SessionID NVARCHAR(64) NOT NULL PRIMARY KEY,
    UserID INT NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT (GETDATE()),
    IPAddress NVARCHAR(45) NULL
);
GO

CREATE NONCLUSTERED INDEX IX_ActiveSessions_UserID ON dbo.ActiveSessions(UserID);
GO

-- Permission-resolution function (copy of sql/NexoraDB/Programmability/Functions/dbo.fnUserHasPermission.sql)
CREATE FUNCTION dbo.fnUserHasPermission
(
    @UserID INT,
    @PermCode SYSNAME
)
RETURNS BIT
AS
BEGIN
    DECLARE @PermID INT;
    SELECT @PermID = PermissionID FROM dbo.Permission WHERE Code = @PermCode;

    IF @PermID IS NULL RETURN 0;

    IF EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride
        WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'D'
    ) RETURN 0;

    IF EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride
        WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'A'
    ) RETURN 1;

    IF EXISTS (
        SELECT 1
        FROM dbo.Users u
        JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessID
        WHERE u.userID = @UserID AND ap.PermissionID = @PermID AND ap.Effect = 'D'
    ) RETURN 0;

    IF EXISTS (
        SELECT 1
        FROM dbo.Users u
        JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessID
        WHERE u.userID = @UserID AND ap.PermissionID = @PermID AND ap.Effect = 'A'
    ) RETURN 1;

    RETURN 0;
END;
GO

-- Stored proc that nx_lib/security.load_permissions_for_user calls
CREATE PROCEDURE dbo.spGetUserPermissions
    @UserID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DISTINCT p.Code
    FROM dbo.Permission p
    WHERE dbo.fnUserHasPermission(@UserID, p.Code) = 1;
END;
GO

-- Reporting SQL tables (Phase 2 live-SQL sandbox, mirrors 0006_create_reporting_sql_tables.sql)
IF OBJECT_ID(N'dbo.ReportingSqlAudit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingSqlAudit (
        Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingSqlAudit PRIMARY KEY,
        UserID        INT NULL,
        Username      NVARCHAR(100) NULL,
        TargetDB      NVARCHAR(50) NOT NULL,
        SqlText       NVARCHAR(MAX) NOT NULL,
        RowsReturned  INT NULL,
        Status        NVARCHAR(16) NOT NULL,
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

-- Saved per-user report definitions (mirrors 0004_create_reports_table.sql) so
-- the saved-report list/load/save flow can be exercised in TEST.
IF OBJECT_ID(N'dbo.Reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Reports (
        ReportID        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Reports PRIMARY KEY,
        OwnerUserID     INT NOT NULL,
        Name            NVARCHAR(200) NOT NULL,
        DefinitionJSON  NVARCHAR(MAX) NOT NULL,
        Visibility      NVARCHAR(20) NOT NULL CONSTRAINT DF_Reports_Visibility DEFAULT 'private',
        CreatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_Reports_Users FOREIGN KEY (OwnerUserID) REFERENCES dbo.Users(userID),
        CONSTRAINT CK_Reports_Visibility CHECK (Visibility IN ('private', 'shared'))
    );
    CREATE INDEX IX_Reports_Owner ON dbo.Reports(OwnerUserID);
END;
GO

-- Scheduled report delivery (mirrors 0012_report_schedules.sql).
IF OBJECT_ID(N'dbo.ReportSchedules', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportSchedules (
        ScheduleID   INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportSchedules PRIMARY KEY,
        ReportID     INT NOT NULL,
        OwnerUserID  INT NOT NULL,
        Recipients   NVARCHAR(1000) NOT NULL,
        Format       NVARCHAR(8) NOT NULL CONSTRAINT DF_ReportSchedules_Format DEFAULT 'xlsx',
        Frequency    NVARCHAR(10) NOT NULL,
        Hour         TINYINT NOT NULL CONSTRAINT DF_ReportSchedules_Hour DEFAULT 6,
        Minute       TINYINT NOT NULL CONSTRAINT DF_ReportSchedules_Minute DEFAULT 0,
        Weekday      TINYINT NULL,
        DayOfMonth   TINYINT NULL,
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportSchedules_Enabled DEFAULT 1,
        LastRunAt    DATETIME2 NULL,
        NextRunAt    DATETIME2 NULL,
        AlertOp      NVARCHAR(8) NULL,
        AlertThreshold FLOAT NULL,
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

-- DB-backed reporting source registry (mirrors 0010_reporting_sources_registry.sql).
IF OBJECT_ID(N'dbo.ReportingSources', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingSources (
        SourceID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingSources PRIMARY KEY,
        Code         NVARCHAR(64) NOT NULL CONSTRAINT UQ_ReportingSources_Code UNIQUE,
        Kind         NVARCHAR(16) NOT NULL,
        Label        NVARCHAR(120) NOT NULL,
        Permission   NVARCHAR(128) NOT NULL,
        Engine       NVARCHAR(32) NULL,
        Target       NVARCHAR(32) NULL,
        Provider     NVARCHAR(32) NULL,
        BaseObject   NVARCHAR(256) NULL,
        ColumnsJSON  NVARCHAR(MAX) NULL,
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportingSources_Enabled DEFAULT 1,
        SortOrder    INT NOT NULL CONSTRAINT DF_ReportingSources_SortOrder DEFAULT 100,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingSources_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingSources_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_ReportingSources_Kind CHECK (Kind IN ('curated', 'sql'))
    );
END;
GO

-- Canonical metrics registry (mirrors 0017_create_reporting_metrics.sql).
IF OBJECT_ID(N'dbo.ReportingMetrics', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingMetrics (
        MetricID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingMetrics PRIMARY KEY,
        Code         NVARCHAR(64) NOT NULL CONSTRAINT UQ_ReportingMetrics_Code UNIQUE,
        SourceId     NVARCHAR(64) NOT NULL,
        Label        NVARCHAR(120) NOT NULL,
        Aggregation  NVARCHAR(16) NOT NULL,
        BaseField    NVARCHAR(128) NULL,
        FilterJson   NVARCHAR(MAX) NULL,
        Description  NVARCHAR(512) NULL,
        Format       NVARCHAR(16) NULL,
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportingMetrics_Enabled DEFAULT 1,
        SortOrder    INT NOT NULL CONSTRAINT DF_ReportingMetrics_SortOrder DEFAULT 100,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_ReportingMetrics_Aggregation
            CHECK (Aggregation IN ('count','count_distinct','sum','avg','min','max'))
    );
END;
GO

-- Explicit per-user report shares (mirrors 0009_report_sharing.sql).
IF OBJECT_ID(N'dbo.ReportShares', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportShares (
        ReportID          INT NOT NULL,
        SharedWithUserID  INT NOT NULL,
        CanEdit           BIT NOT NULL CONSTRAINT DF_ReportShares_CanEdit DEFAULT 0,
        CreatedAt         DATETIME2 NOT NULL
                          CONSTRAINT DF_ReportShares_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_ReportShares PRIMARY KEY (ReportID, SharedWithUserID),
        CONSTRAINT FK_ReportShares_Reports FOREIGN KEY (ReportID)
            REFERENCES dbo.Reports(ReportID) ON DELETE CASCADE,
        CONSTRAINT FK_ReportShares_Users FOREIGN KEY (SharedWithUserID)
            REFERENCES dbo.Users(userID)
    );
    CREATE INDEX IX_ReportShares_User ON dbo.ReportShares(SharedWithUserID);
END;
GO
