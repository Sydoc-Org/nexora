-- 0004_name_the_constraints.sql
-- Issue #220, phase 1: give every auto-named constraint a deterministic name.
-- Metadata only -- no data moves, no code changes.
--
-- 22 of the 24 primary keys are compiler-generated (PK__Dokument__3214EC271A02B9B9),
-- as are 5 default constraints (DF__ReportJob__Inser__7849DB76). The hash suffix
-- is assigned at CREATE time, so INT and PROD carry *different* names for the
-- same constraint and sql/sync-from-db.py re-dumps a diff every time someone
-- re-syncs. The 14 foreign keys are named after the column (FK_DOC_NK1) rather
-- than the relationship, which is why nobody can tell what NK1 points at.
--
-- Target names (D3 in docs/superpowers/plans/2026-08-27-generali-db-restructure.md):
--   PK_<Table>
--   FK_<Table>_<ReferencedTable>[_<Role>]   role only when the same pair is
--                                           joined twice (NK1 / NK2)
--   DF_<Table>_<Column>
--
-- Every rename is driven off the system catalogs and matched by TABLE and
-- COLUMN, never by the current name -- that is the whole point, since the
-- current names differ per environment. Re-running renames nothing.
--
-- Table names stay German here on purpose; phase 2 of #220 renames the tables
-- and these constraint names follow then.

SET NOCOUNT ON;

DECLARE @sql nvarchar(max) = N'';

-- Primary keys -> PK_<Table>
SELECT @sql = @sql
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(kc.name) + N''', N''PK_' + t.name + N''', ''OBJECT'';' + CHAR(10)
FROM sys.key_constraints kc
JOIN sys.tables t ON t.object_id = kc.parent_object_id
WHERE kc.type = 'PK'
  AND kc.name <> N'PK_' + t.name;

-- Foreign keys -> FK_<Table>_<ReferencedTable>[_<Role>]
-- Role suffix = the parent column minus its DOC_ prefix, added only when the
-- same (parent, referenced) pair carries more than one key (DOC_NK1/DOC_NK2).
SELECT @sql = @sql
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(f.fk_name) + N''', N''' + f.target + N''', ''OBJECT'';' + CHAR(10)
FROM (
    SELECT fk.name AS fk_name,
           N'FK_' + pt.name + N'_' + rt.name
             + CASE WHEN COUNT(*) OVER (PARTITION BY fk.parent_object_id, fk.referenced_object_id) > 1
                    THEN N'_' + CASE WHEN pc.name LIKE 'DOC[_]%' THEN STUFF(pc.name, 1, 4, N'') ELSE pc.name END
                    ELSE N'' END AS target
    FROM sys.foreign_keys fk
    JOIN sys.tables pt ON pt.object_id = fk.parent_object_id
    JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
    JOIN sys.foreign_key_columns fkc
      ON fkc.constraint_object_id = fk.object_id AND fkc.constraint_column_id = 1
    JOIN sys.columns pc
      ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
) AS f
WHERE f.fk_name <> f.target;

-- Default constraints -> DF_<Table>_<Column>
SELECT @sql = @sql
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(dc.name) + N''', N''DF_' + t.name + N'_' + c.name + N''', ''OBJECT'';' + CHAR(10)
FROM sys.default_constraints dc
JOIN sys.tables t ON t.object_id = dc.parent_object_id
JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
WHERE dc.name <> N'DF_' + t.name + N'_' + c.name;

IF @sql = N''
    PRINT 'Migration 0004: every constraint already carries its target name, nothing to do.';
ELSE
BEGIN
    PRINT @sql;
    EXEC sp_executesql @sql;
END
GO
