-- 0045_add_active_sessions_last_seen.sql
-- Issue #109: the "Active Sessions" admin page and the overview KPI both
-- claim a short window (page: "last 30 minutes", overview design doc:
-- "Active users (5 min)") but actually filter on ActiveSessions.CreatedAt,
-- which is set once at login and never updated -- so both really show
-- "logged in within the last 24 hours", not "currently active".
-- Add LastSeenAt so the per-request enforcement hook (nx_lib/hooks.py) can
-- bump it on every request; the admin views then filter on it instead.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.ActiveSessions') AND name = 'LastSeenAt'
)
BEGIN
    ALTER TABLE dbo.ActiveSessions ADD LastSeenAt datetime NULL;
END
GO

UPDATE dbo.ActiveSessions SET LastSeenAt = CreatedAt WHERE LastSeenAt IS NULL;
GO

ALTER TABLE dbo.ActiveSessions ALTER COLUMN LastSeenAt datetime NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = 'IX_ActiveSessions_LastSeenAt' AND object_id = OBJECT_ID('dbo.ActiveSessions')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ActiveSessions_LastSeenAt ON dbo.ActiveSessions (LastSeenAt);
END
GO
