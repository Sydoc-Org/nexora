-- 0049_add_users_last_login_at.sql
-- Issue #146: the dashboard's once-per-login sign-in note also shows when the
-- account was last used before this login. ActiveSessions can't answer that --
-- its rows are deleted on logout/revoke -- so keep the previous login stamp on
-- the user row. Written by _record_active_session() on every login path.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.Users') AND name = 'LastLoginAt'
)
BEGIN
    ALTER TABLE dbo.Users ADD LastLoginAt datetime NULL;
END
GO
