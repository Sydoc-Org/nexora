-- 0103_repoint_doc_count_reports.sql
-- Repairs 0102. Its two UPDATE statements matched nothing and silently did
-- nothing, so doc_count was disabled with the five saved reports still pointing
-- at it -- exactly the breakage 0102 set out to avoid.
--
-- The bug was in the guard, not the intent: T-SQL LIKE treats '[' as the start
-- of a character class, so the pattern
--
--     '%"metrics": [{"metric": "doc_count"}]%'
--
-- was read as "a literal '{', '\"', 'm', 'e', ... or 'c'" and never matched a
-- real definition. It failed open (0 rows), which is why the migration reported
-- success.
--
-- So this one does not pattern-match JSON as text at all. The metrics array is
-- inspected with JSON_VALUE, which parses it properly and has no escaping
-- surprises. Only the date-field guards stay as LIKE, and those contain no
-- wildcard-significant characters.
--
-- Everything else is 0102's contract, unchanged: only a docprocessing report
-- whose metrics array is exactly one doc_count, and whose every date reference
-- is the same field, is touched. An anchored measure plots on the shared
-- activity_date axis, so the column, filter and sort move with the metric --
-- a definition anchored on docs_imported but grouped on import_date is rejected
-- by the server. The numbers do not change: counting rows grouped by import
-- month is what docs_imported does. The inner title is refreshed from the
-- report's own Name (never invented text) because these carry the stale title
-- "Document count per month" while being named for import or export.
--
-- Anything not matching is left alone and keeps doc_count -- it stops
-- resolving, and its owner rebuilds it. Idempotent: after this runs, no
-- definition has a lone doc_count metric left to match.

-- 1) Import-anchored: exactly one doc_count metric, import_date only.
UPDATE dbo.Reports
SET DefinitionJSON = JSON_MODIFY(
        REPLACE(
            REPLACE(DefinitionJSON,
                    '"metric": "doc_count"', '"metric": "docs_imported"'),
            '"import_date"', '"activity_date"'),
        '$.title', Name)
WHERE JSON_VALUE(DefinitionJSON, '$.source') = 'docprocessing'
  AND JSON_VALUE(DefinitionJSON, '$.metrics[0].metric') = 'doc_count'
  AND JSON_VALUE(DefinitionJSON, '$.metrics[1].metric') IS NULL
  AND DefinitionJSON LIKE '%import_date%'
  AND DefinitionJSON NOT LIKE '%export_date%'
  AND DefinitionJSON NOT LIKE '%activity_date%';
GO

-- 2) Export-anchored: the mirror image.
UPDATE dbo.Reports
SET DefinitionJSON = JSON_MODIFY(
        REPLACE(
            REPLACE(DefinitionJSON,
                    '"metric": "doc_count"', '"metric": "docs_exported"'),
            '"export_date"', '"activity_date"'),
        '$.title', Name)
WHERE JSON_VALUE(DefinitionJSON, '$.source') = 'docprocessing'
  AND JSON_VALUE(DefinitionJSON, '$.metrics[0].metric') = 'doc_count'
  AND JSON_VALUE(DefinitionJSON, '$.metrics[1].metric') IS NULL
  AND DefinitionJSON LIKE '%export_date%'
  AND DefinitionJSON NOT LIKE '%import_date%'
  AND DefinitionJSON NOT LIKE '%activity_date%';
GO

-- 3) Re-assert 0102's intent, in case only part of that migration's effect is
--    present in a given environment.
UPDATE dbo.ReportingMetrics
SET Enabled = 0
WHERE Code = 'doc_count';
GO
