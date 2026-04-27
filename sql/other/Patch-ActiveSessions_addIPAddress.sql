-- Adds IPAddress column to an existing ActiveSessions table.
-- Idempotent: safe to run more than once.

IF EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[ActiveSessions]') AND type = 'U')
   AND NOT EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id = OBJECT_ID(N'[dbo].[ActiveSessions]') AND name = 'IPAddress'
   )
BEGIN
    ALTER TABLE dbo.ActiveSessions ADD IPAddress NVARCHAR(45) NULL;
END;
