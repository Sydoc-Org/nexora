-- 0046_drop_permission_sortingcode.sql
-- Sorting Code field removed from the permission editor (issue #110): drop the
-- now-unused dbo.Permission.SortingCode column added by 0034.
-- Idempotent: guarded, naturally re-runnable.

IF COL_LENGTH('dbo.Permission', 'SortingCode') IS NOT NULL
    ALTER TABLE dbo.Permission DROP COLUMN SortingCode;
GO
