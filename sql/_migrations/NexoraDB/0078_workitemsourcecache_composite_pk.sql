-- 0078: WorkitemSourceCache PK (WorkItemID) -> (WorkItemID, ClientCode) (#98).
-- Ids collide across clients (1216 on INT); a single-column PK could only
-- ever pin one client per id. Reader treats >1 row per id as ambiguous.
DECLARE @pk sysname = (
    SELECT kc.name FROM sys.key_constraints kc
    WHERE kc.parent_object_id = OBJECT_ID('dbo.WorkitemSourceCache') AND kc.type = 'PK'
      AND 1 = (SELECT COUNT(*) FROM sys.index_columns ic
               WHERE ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id)
);
IF @pk IS NOT NULL
    EXEC('ALTER TABLE dbo.WorkitemSourceCache DROP CONSTRAINT ' + @pk);
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints
               WHERE parent_object_id = OBJECT_ID('dbo.WorkitemSourceCache') AND type = 'PK')
    ALTER TABLE dbo.WorkitemSourceCache
        ADD CONSTRAINT PK_WorkitemSourceCache PRIMARY KEY CLUSTERED (WorkItemID, ClientCode);
GO
