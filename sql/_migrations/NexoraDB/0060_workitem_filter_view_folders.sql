-- 0059: optional folder/category for saved workitem filter views (issue #186).
-- NULL = un-foldered (a folder is an option, not a requirement); the chips bar
-- groups same-folder views behind one folder chip. Idempotent.
IF COL_LENGTH('dbo.WorkitemFilterViews', 'Folder') IS NULL
    ALTER TABLE dbo.WorkitemFilterViews ADD Folder NVARCHAR(100) NULL;
GO
