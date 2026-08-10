-- Durable per-account login lockout (#193 finding 7). flask_limiter's
-- per-worker in-memory IP rate limit has no account-level backstop, so a
-- distributed password-spray against one known account only faces
-- per-worker-per-IP throttling. This table is a global (cross-worker,
-- cross-IP) failed-attempt counter keyed on userid.
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'LoginLockout')
BEGIN
    CREATE TABLE dbo.LoginLockout (
        userid NVARCHAR(64) NOT NULL PRIMARY KEY,
        failed_count INT NOT NULL DEFAULT 0,
        locked_until DATETIME2 NULL,
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END
GO
