-- 0004_create_reports_table.sql
-- Per-user saved report definitions for the Reporting page. DefinitionJSON holds
-- the v1 report definition validated by nx_lib.reporting.schema. Sharing is
-- deferred; OwnerUserID scopes visibility for now.
IF OBJECT_ID(N'dbo.Reports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Reports (
        ReportID        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Reports PRIMARY KEY,
        OwnerUserID     INT NOT NULL,
        Name            NVARCHAR(200) NOT NULL,
        DefinitionJSON  NVARCHAR(MAX) NOT NULL,
        CreatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2 NOT NULL CONSTRAINT DF_Reports_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_Reports_Users FOREIGN KEY (OwnerUserID) REFERENCES dbo.Users(userID)
    );
    CREATE INDEX IX_Reports_Owner ON dbo.Reports(OwnerUserID);
END;
GO
