-- 0009_report_sharing.sql
-- Cross-user report sharing for the Reporting page. Two mechanisms:
--   1. A Visibility flag on dbo.Reports: 'private' (default, owner-only) or
--      'shared' (visible read-only to everyone who can open the Reporting page).
--   2. An explicit per-user grant table dbo.ReportShares, optionally read-write
--      (CanEdit), so a private report can be shared with named colleagues.
-- Idempotent throughout.

IF COL_LENGTH('dbo.Reports', 'Visibility') IS NULL
BEGIN
    ALTER TABLE dbo.Reports
        ADD Visibility NVARCHAR(20) NOT NULL
            CONSTRAINT DF_Reports_Visibility DEFAULT 'private';
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_Reports_Visibility')
BEGIN
    ALTER TABLE dbo.Reports
        ADD CONSTRAINT CK_Reports_Visibility CHECK (Visibility IN ('private', 'shared'));
END;
GO

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
