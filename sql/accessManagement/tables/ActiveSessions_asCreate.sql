-- ActiveSessions
-- Tracks issued Flask-Session session IDs per user for admin force-logout.
-- Populated by _record_active_session in the login flow.
-- Cleared by admin revoke endpoints (/admin/sessions/<sid>/revoke and
-- /admin/users/<id>/revoke_all). Stale rows where the on-disk session file
-- has expired are not auto-pruned in this phase; a future cleanup job may
-- reconcile this table against SESSION_FILE_DIR.

IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[ActiveSessions]') AND type = 'U')
BEGIN
    CREATE TABLE dbo.ActiveSessions (
        SessionID NVARCHAR(64) NOT NULL PRIMARY KEY,
        UserID    INT          NOT NULL,
        CreatedAt DATETIME     NOT NULL CONSTRAINT DF_ActiveSessions_CreatedAt DEFAULT (GETDATE())
    );

    CREATE INDEX IX_ActiveSessions_UserID ON dbo.ActiveSessions(UserID);
END;
