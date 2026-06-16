-- 0023_create_workitem_source_cache.sql
-- Routing cache for multi-source workitems: which client/runtime DB owns a
-- given workitem id. Self-populating (the merged list warms it; the detail
-- route probes-then-caches on a miss). No seed rows.
IF NOT EXISTS (
    SELECT 1 FROM sys.tables WHERE name = 'WorkitemSourceCache' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.WorkitemSourceCache (
        WorkItemID  NVARCHAR(255) NOT NULL,
        ClientCode  NVARCHAR(50)  NOT NULL,
        ResolvedAt  DATETIME2     NOT NULL CONSTRAINT DF_WorkitemSourceCache_ResolvedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_WorkitemSourceCache PRIMARY KEY (WorkItemID)
    );
END
GO
