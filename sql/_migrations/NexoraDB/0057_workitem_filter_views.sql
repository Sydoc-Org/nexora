-- 0057: per-user saved workitem filter views (issue #170).
-- Stores the serialized filter-form state of the workitems list so a user can
-- re-apply a named combination ("PDBS backlog", "my validation queue") with one
-- click. Private per user; FilterJSON is the client-side [name, value] pair
-- list the page already builds for /api/workitems. Idempotent.
IF OBJECT_ID(N'dbo.WorkitemFilterViews', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.WorkitemFilterViews (
        ID         INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_WorkitemFilterViews PRIMARY KEY,
        UserID     INT NOT NULL,
        Name       NVARCHAR(100) NOT NULL,
        FilterJSON NVARCHAR(MAX) NOT NULL,
        SortOrder  INT NOT NULL CONSTRAINT DF_WorkitemFilterViews_SortOrder DEFAULT 0,
        CreatedAt  DATETIME2 NOT NULL CONSTRAINT DF_WorkitemFilterViews_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_WorkitemFilterViews_Users FOREIGN KEY (UserID) REFERENCES dbo.Users(userID) ON DELETE CASCADE,
        CONSTRAINT UQ_WorkitemFilterViews_User_Name UNIQUE (UserID, Name)
    );
END
GO
