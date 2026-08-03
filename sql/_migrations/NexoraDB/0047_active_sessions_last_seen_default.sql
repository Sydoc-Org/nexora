-- 0047_active_sessions_last_seen_default.sql
-- Regression from 0045: LastSeenAt was made NOT NULL with no DEFAULT, but the
-- INSERTs in nx_lib/views/auth.py (_record_active_session) never supplied it.
-- Every login therefore failed to record its session, and the next request hit
-- _enforce_active_session, found no ActiveSessions row, and cleared the session
-- -- i.e. nobody could stay logged in. CreatedAt already carries DEFAULT
-- (getdate()); give LastSeenAt the same so every INSERT site is fixed at once
-- (the hook still bumps it per request).

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE name = 'DF_ActiveSessions_LastSeenAt'
)
BEGIN
    ALTER TABLE dbo.ActiveSessions
        ADD CONSTRAINT DF_ActiveSessions_LastSeenAt DEFAULT (getdate()) FOR LastSeenAt;
END
GO
