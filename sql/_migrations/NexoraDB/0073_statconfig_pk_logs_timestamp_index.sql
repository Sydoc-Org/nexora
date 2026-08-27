-- 0073: schema-hygiene quick wins (#98).
--
-- * dbo.StatConfig was a PK-less heap whose de-facto key column was nullable.
--   Verified on INT and PROD 2026-08-26: 6 rows each, no NULL ProcessName, no
--   (ProcessName, ClientCode) duplicates — the composite PK just makes the row
--   identity the code already assumes explicit.
-- * dbo.Logs only had its identity PK; the admin log pages filter and sort on
--   Timestamp, which scans the whole table as the log grows.
--
-- Idempotent: guarded, safe for the pre-commit hook to re-apply.

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.StatConfig')
      AND name = 'ProcessName' AND is_nullable = 1
)
    ALTER TABLE dbo.StatConfig ALTER COLUMN ProcessName NVARCHAR(100) NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID('dbo.StatConfig') AND type = 'PK'
)
    ALTER TABLE dbo.StatConfig
        ADD CONSTRAINT PK_StatConfig PRIMARY KEY CLUSTERED (ProcessName, ClientCode);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.Logs') AND name = 'IX_Logs_Timestamp'
)
    CREATE NONCLUSTERED INDEX IX_Logs_Timestamp ON dbo.Logs ([Timestamp] DESC);
GO
