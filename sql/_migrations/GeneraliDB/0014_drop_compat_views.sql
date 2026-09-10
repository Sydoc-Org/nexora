-- 0014_drop_compat_views.sql
-- Issue #220, phase 6.1 + 6.2: take down the scaffolding from phases 2 and 3.
--
-- Every rename in this restructure left the old name behind as a view, because
-- deploy.yml applies migrations to PROD *before* it stops the app pool, so for
-- a few seconds the old code runs against the new schema (D8). Phases 1-4 are
-- all live on PROD, so the code that needed these names is gone and the views
-- are dead weight in every schema listing, every re-dump and every drawing the
-- reporting source visualizer makes of this database.
--
-- The two gates the plan put on this step are both met:
--
--   Q3, external consumers -- answered "no" by the owner. Re-checked against
--   INT's Query Store as well: no reader outside this repo.
--
--   Ordering -- the plan said "one release after phase 3 ships to PROD".
--   Phases 1-4 shipped in PR #318 (24e87fad) and #319 (5f4de843) and are on
--   PROD; prdimpexp01 runs the matching csvToSql.ps1. Nothing in the app or
--   the importer names any of these views: verified by grep over nx_lib,
--   scripts, templates and tests, and by ReportingSources.BaseObject, which
--   points every one of the seven Generali sources at a real table or at
--   v_Documents.
--
-- NOT DROPPED, and why:
--
--   dbo.v_Documents -- not scaffolding. It is the resolved view the app reads
--   in all 12 of its Documents queries, and the base object of the
--   generali_documents reporting source.
--
--   dbo.CategoryTranslations -- created *as* a view by 0013, one release ago
--   from its own point of view. Same D8 rule; it goes in the next release.
--
--   The phase-4 legacy text columns. The plan's 6.1 listed them here, written
--   when 4.1 was going to backfill Amount/Quantity/VoucherDate/IsPending into
--   stored columns. It did not: they shipped as *computed* columns over
--   AmountText/QuantityText/VoucherDateText/PendingText, so the text columns
--   are the data, not a legacy copy of it. Dropping them would drop the
--   typed columns with them. Nothing to do here.
--
-- Reversible: every one of these views is a SELECT over tables that still
-- exist, and the definitions are in this repo's history (migrations 0005 and
-- 0007). Idempotent, and refuses to drop anything if a successor is missing.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- Refuse to run at all if the tables these views forward to are not there --
-- that would mean a rename went wrong and one of these "views" is the data.
IF OBJECT_ID(N'dbo.Documents',              N'U') IS NULL
   OR OBJECT_ID(N'dbo.AttendanceEntries',   N'U') IS NULL
   OR OBJECT_ID(N'dbo.BaseServiceEntries',  N'U') IS NULL
   OR OBJECT_ID(N'dbo.ProjectEntries',      N'U') IS NULL
   OR OBJECT_ID(N'dbo.QualityCheckEntries', N'U') IS NULL
   OR OBJECT_ID(N'dbo.IssReports',          N'U') IS NULL
   OR OBJECT_ID(N'dbo.ImportRuns',          N'U') IS NULL
   OR OBJECT_ID(N'dbo.EffortCategories',    N'U') IS NULL
   OR OBJECT_ID(N'dbo.QualityCheckCategories', N'U') IS NULL
   OR OBJECT_ID(N'dbo.v_Documents',         N'V') IS NULL
    THROW 50014, 'A renamed target is missing; refusing to drop the compatibility views.', 1;
GO

DECLARE @views TABLE (Name sysname);
INSERT INTO @views (Name) VALUES
    (N'AdditionalServices'),          -- -> EffortCategories        (0005)
    (N'Attendance'),                  -- -> AttendanceEntries       (0005)
    (N'BaseServices'),                -- -> BaseServiceEntries      (0005)
    (N'CategoryTranslation'),         -- -> CategoryTranslations    (0005)
    (N'CSVImportLog'),                -- -> ImportRuns              (0005)
    (N'PDQMMapping'),                 -- -> QualityCheckCategories  (0005)
    (N'PDQMReport'),                  -- -> QualityCheckEntries     (0005)
    (N'ProjectManagement'),           -- -> ProjectEntries          (0005)
    (N'ReportingISS'),                -- -> IssReports              (0005)
    (N'ReportJob'),                   -- -> Documents               (0007)
    (N'v_ReportJobJoinDefinitions');  -- -> v_Documents             (0007, phase 6.2)

DECLARE @name sysname, @sql nvarchar(400);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT Name FROM @views;
OPEN c;
FETCH NEXT FROM c INTO @name;
WHILE @@FETCH_STATUS = 0
BEGIN
    -- 'V' only: if the name is still a table, a rename never happened and this
    -- would be data loss, not cleanup.
    IF OBJECT_ID(QUOTENAME(N'dbo') + N'.' + QUOTENAME(@name), N'V') IS NOT NULL
    BEGIN
        SET @sql = N'DROP VIEW ' + QUOTENAME(N'dbo') + N'.' + QUOTENAME(@name) + N';';
        EXEC sp_executesql @sql;
    END
    ELSE IF OBJECT_ID(QUOTENAME(N'dbo') + N'.' + QUOTENAME(@name), N'U') IS NOT NULL
    BEGIN
        CLOSE c; DEALLOCATE c;
        THROW 50014, 'A compatibility name is still a base table; refusing to drop it.', 1;
    END

    FETCH NEXT FROM c INTO @name;
END
CLOSE c;
DEALLOCATE c;
GO
