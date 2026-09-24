-- 0006_qualitycheckcategories_primary_key.sql
-- Issue #220, phase 2 follow-up: dbo.QualityCheckCategories (was PDQMMapping)
-- is the only table in this database with no primary key at all.
--
-- Found while verifying 0005: 24 tables, 23 primary keys. The table has had an
-- `ID int IDENTITY NOT NULL` column since it was created, so nothing in the
-- data has to change -- the constraint was simply never declared, which is
-- also why 0004 had 22 auto-named PKs to rename instead of 23.
--
-- 27 rows. Idempotent.

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID('dbo.QualityCheckCategories') AND type = 'PK'
)
    ALTER TABLE dbo.QualityCheckCategories
        ADD CONSTRAINT PK_QualityCheckCategories PRIMARY KEY CLUSTERED (ID);
GO
