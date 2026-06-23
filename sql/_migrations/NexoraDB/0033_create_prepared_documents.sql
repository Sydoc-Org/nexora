-- 0033_create_prepared_documents.sql
-- MS02-only standalone 'prepared documents' intake register. Accumulating,
-- upsert-by-PID; shared across MS02 users; read-only + clear-whole-list (v1).
-- Gated by workitems.import.preparedaudit + ms02_active at runtime. Replaces the
-- transient session-overlay pidImport model. No ClientCode column (MS02-only,
-- YAGNI). No new permission (workitems.import.preparedaudit reused from 0029).
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'PreparedDocuments' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.PreparedDocuments (
        ID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PreparedDocuments PRIMARY KEY,
        PID         NVARCHAR(100) NOT NULL,
        Collected   BIT NOT NULL CONSTRAINT DF_PreparedDocuments_Collected DEFAULT (0),
        CollectedBy NVARCHAR(255) NULL,
        Prepared    BIT NOT NULL CONSTRAINT DF_PreparedDocuments_Prepared DEFAULT (0),
        PreparedBy  NVARCHAR(255) NULL,
        UploadedBy  INT NULL,
        UploadedAt  DATETIME2 NOT NULL CONSTRAINT DF_PreparedDocuments_UploadedAt DEFAULT (SYSUTCDATETIME()),
        UpdatedAt   DATETIME2 NULL,
        CONSTRAINT UQ_PreparedDocuments_PID UNIQUE (PID)
    );
END
GO
