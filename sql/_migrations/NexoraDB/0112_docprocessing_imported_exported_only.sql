-- 0102_docprocessing_imported_exported_only.sql
-- Issue #254 follow-up. "Document count" leaves the wizard so the measure list
-- reads as a clear either/or: a document is counted on the day it was IMPORTED
-- or on the day it was EXPORTED, never on an unanchored "just count the rows".
--
-- doc_count is not dead weight though -- five saved reports on INT use it, four
-- of them named "Documents imported/exported per month" but built on doc_count
-- because they predate docs_imported/docs_exported. Disabling the measure under
-- them would 400 every one. So those are repointed first.
--
-- The repoint is NOT a measure swap. An anchored measure plots on the shared
-- activity_date axis, so the date column, the filter and the sort all have to
-- move from import_date/export_date to activity_date -- a definition whose
-- metric is anchored but whose column is import_date is rejected by the server.
-- The numbers are unchanged: counting rows grouped by import month is exactly
-- what docs_imported does.
--
-- Deliberately conservative -- this rewrites saved reports, including other
-- people's, and it runs on PROD where the shapes are unknown. A report is only
-- touched when its shape is unambiguous:
--
--   * source is docprocessing, and
--   * its metrics array is EXACTLY [{"metric": "doc_count"}] -- one measure,
--     so there is no second metric whose axis this would break, and
--   * every date reference is the same field: import_date with no export_date
--     and no activity_date anywhere, or the mirror image.
--
-- Anything else -- two measures, a mixed date, a shape we do not recognise --
-- is left alone and keeps doc_count. Those reports stop resolving, same as
-- #35 "Document count per month" on INT, and their owner rebuilds them. That
-- is the deliberate trade: a report we do not fully understand is left for a
-- human rather than rewritten by a migration.
--
-- The definition's inner `title` is also refreshed, but only from the report's
-- own Name -- never invented text -- because those four carry the stale title
-- "Document count per month" while being named for import or export. JSON_MODIFY
-- rather than REPLACE so the JSON escaping of the name is SQL Server's problem.
--
-- Idempotent: after it runs, nothing matches the doc_count guards any more.

-- 1a) Import-anchored: doc_count + import_date only.
UPDATE dbo.Reports
SET DefinitionJSON = JSON_MODIFY(
        REPLACE(
            REPLACE(DefinitionJSON,
                    '"metric": "doc_count"', '"metric": "docs_imported"'),
            '"import_date"', '"activity_date"'),
        '$.title', Name)
WHERE DefinitionJSON LIKE '%"source": "docprocessing"%'
  AND DefinitionJSON LIKE '%"metrics": [{"metric": "doc_count"}]%'
  AND DefinitionJSON LIKE '%"import_date"%'
  AND DefinitionJSON NOT LIKE '%"export_date"%'
  AND DefinitionJSON NOT LIKE '%"activity_date"%';
GO

-- 1b) Export-anchored: the mirror image.
UPDATE dbo.Reports
SET DefinitionJSON = JSON_MODIFY(
        REPLACE(
            REPLACE(DefinitionJSON,
                    '"metric": "doc_count"', '"metric": "docs_exported"'),
            '"export_date"', '"activity_date"'),
        '$.title', Name)
WHERE DefinitionJSON LIKE '%"source": "docprocessing"%'
  AND DefinitionJSON LIKE '%"metrics": [{"metric": "doc_count"}]%'
  AND DefinitionJSON LIKE '%"export_date"%'
  AND DefinitionJSON NOT LIKE '%"import_date"%'
  AND DefinitionJSON NOT LIKE '%"activity_date"%';
GO

-- 2) Now the measure can go. Disabled, not deleted: dbo.ReportingMetrics is
--    read WHERE Enabled = 1, so this is one UPDATE away from coming back and
--    the definition stays on record.
UPDATE dbo.ReportingMetrics
SET Enabled = 0
WHERE Code = 'doc_count';
GO
