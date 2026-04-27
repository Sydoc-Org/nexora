IF NOT EXISTS (SELECT 1 FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[ActiveSessions]') AND type = 'U')
BEGIN
    CREATE TABLE dbo.ActiveSessions (
        SessionID NVARCHAR(64) NOT NULL PRIMARY KEY,
        UserID    INT          NOT NULL,
        IPAddress NVARCHAR(45) NULL,
        CreatedAt DATETIME     NOT NULL CONSTRAINT DF_ActiveSessions_CreatedAt DEFAULT (GETDATE())
    );

    CREATE INDEX IX_ActiveSessions_UserID ON dbo.ActiveSessions(UserID);
END
ELSE IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'[dbo].[ActiveSessions]') AND name = 'IPAddress'
)
BEGIN
    ALTER TABLE dbo.ActiveSessions ADD IPAddress NVARCHAR(45) NULL;
END;
