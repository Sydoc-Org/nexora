-- 0003_reportjob_keys_and_indexes.sql
-- Issue #220, phase 1: give dbo.ReportJob the two indexes it has always needed.
-- Nothing is renamed and no column changes type, so no application code moves
-- with this migration.
--
-- Until now ReportJob (2,682,707 rows / 1,366 MB on INT 2026-09-10) carried
-- exactly ONE index: the clustered PK on the surrogate RecordID. Every access
-- path was therefore a full scan of the whole table.
--
-- Measured on the live INT copy, 2026-09-10:
--
--   scripts/generali-import/*/csvToSql.ps1 MERGEs on DOC_ID in batches of 500.
--   Plan before: Hash Match + full Clustered Index Scan per batch. After:
--   Nested Loops + Index Seek.  500-row batch 3,169 ms -> 2,435 ms (-23%).
--   A daily CSV is ~16k-25k rows = 32-50 batches, so ~25-35 s off a ~320 s run.
--   (The rest of that 320 s is the PowerShell side building a 500-row VALUES
--   literal per batch; a table-valued parameter would be the next win, but that
--   is an importer change, not a schema one.)
--
--   /generali/documents document-detail (SELECT * FROM v_ReportJobJoinDefinitions
--   WHERE DOC_ID = ?) was a full scan on every single document opened.
--
--   The dashboard filters and groups by DOC_SCANDATUM in every query. With the
--   covering index below: KPI 250 -> 25 ms, trend 303 -> 46 ms, latest-day probe
--   310 -> 68 ms, doctype breakdown 279 -> 58 ms (warm cache, INT).
--
-- Index sizes on INT: UQ_ReportJob_DOC_ID 136 MB, IX_ReportJob_DOC_SCANDATUM
-- 143 MB. Build time ~9 s each. Standard Edition has no ONLINE index build, so
-- both take a schema lock on ReportJob while they build -- seconds, but do not
-- run this migration while the 12:05 import is running.
--
-- Deliberately NOT created: separate IX on DOC_DOKUMENTENTYP and
-- DOC_DOKUMENTENSTATUS. The covering index below already serves the two group-by
-- queries that motivated them (measured, above), and DOC_DOKUMENTENSTATUS is not
-- referenced anywhere in nx_lib/views/generali/. Not tuned: FILLFACTOR and
-- DATA_COMPRESSION -- both want a maintenance job that does not exist yet.
--
-- Idempotent.

-- A filtered index cannot be created unless both of these are ON, and sqlcmd
-- (which scripts/db-migrate.py shells out to) leaves QUOTED_IDENTIFIER OFF.
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- DOC_ID is what the nightly MERGE matches on and is unique across all
-- 2,682,707 rows. Fail loudly rather than let CREATE UNIQUE INDEX abort a
-- deploy with "a duplicate key was found" and no context.
IF EXISTS (
    SELECT 1 FROM dbo.ReportJob
    WHERE DOC_ID IS NOT NULL
    GROUP BY DOC_ID HAVING COUNT(*) > 1
)
    THROW 50220, 'Migration 0003: dbo.ReportJob.DOC_ID is not unique. The daily CSV MERGE assumes it is (ON t.DOC_ID = s.DOC_ID). Resolve the duplicates before creating UQ_ReportJob_DOC_ID.', 1;
GO

-- Filtered on IS NOT NULL on purpose: csvToSql.ps1 explicitly lets rows with a
-- NULL DOC_ID through (`WHERE rn = 1 OR [DOC_ID] IS NULL`), and an unfiltered
-- UNIQUE index would break the import the first night two such rows arrive.
-- Verified on INT that the optimiser still matches this filtered index for the
-- MERGE's join predicate and turns the plan into an Index Seek.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.ReportJob') AND name = 'UQ_ReportJob_DOC_ID'
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ReportJob_DOC_ID
        ON dbo.ReportJob (DOC_ID)
        WHERE DOC_ID IS NOT NULL;
GO

-- Covers the /generali/documents dashboard: every one of its queries filters on
-- DOC_SCANDATUM and then needs the view's own InterfaceLink filter plus one
-- grouping column. The INCLUDE list is exactly the lookup FKs the app reads --
-- adding more would grow the index without covering anything.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('dbo.ReportJob') AND name = 'IX_ReportJob_DOC_SCANDATUM'
)
    CREATE NONCLUSTERED INDEX IX_ReportJob_DOC_SCANDATUM
        ON dbo.ReportJob (DOC_SCANDATUM)
        INCLUDE (
            DOC_INTERFACE_LINK,   -- v_ReportJobJoinDefinitions filters on this
            DOC_KOMMUNIKATION,
            DOC_DOKUMENTENTYP,
            DOC_EMPFAENGER,
            DOC_SPRACHE,
            DOC_EINGANGSKANAL,
            DOC_NK1,
            DOC_NK2
        );
GO
