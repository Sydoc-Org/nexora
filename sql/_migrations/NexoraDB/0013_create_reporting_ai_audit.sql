-- 0013_create_reporting_ai_audit.sql
-- Phase 1 AI assistant: audit log of every NL->SQL interaction. Schema-only
-- egress (the prompt + generated SQL are recorded; never result rows). Idempotent.
IF OBJECT_ID(N'dbo.ReportingAiAudit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingAiAudit (
        Id            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingAiAudit PRIMARY KEY,
        UserID        INT NULL,
        Username      NVARCHAR(100) NULL,
        Prompt        NVARCHAR(MAX) NOT NULL,
        Surface       NVARCHAR(16) NOT NULL,   -- sql (Phase 1 only)
        GeneratedSql  NVARCHAR(MAX) NULL,
        Model         NVARCHAR(100) NULL,
        Provider      NVARCHAR(32) NULL,
        TokensIn      INT NULL,
        TokensOut     INT NULL,
        GateVerdict   NVARCHAR(16) NULL,       -- valid | invalid | na
        Status        NVARCHAR(16) NOT NULL,   -- ok | error
        DurationMs    INT NULL,
        CreatedAt     DATETIME2 NOT NULL
                      CONSTRAINT DF_ReportingAiAudit_CreatedAt DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_ReportingAiAudit_User ON dbo.ReportingAiAudit(UserID, CreatedAt);
END;
GO
