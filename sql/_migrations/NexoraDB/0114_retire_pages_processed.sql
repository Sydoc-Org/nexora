-- 0104_retire_pages_processed.sql
-- Issue #254 follow-up to 0102/0103. "Pages processed" (page_count) comes off
-- the wizard, finishing what those started.
--
-- Document Processing now answers one question consistently: was a document (or
-- a page) counted on the day it was IMPORTED or the day it was EXPORTED.
-- page_count was the last measure that answered neither -- an unanchored
-- SUM(pagecount) over whatever happened to be in scope. Keeping it meant the
-- category read as five anchored measures plus one that behaved differently,
-- and the anchor rule made that visible in the worst way: page_count was the
-- only chip that greyed out when any of the other five was picked, and the only
-- one that greyed out all five when picked itself.
--
-- pages_imported / pages_exported already cover the same numbers with a stated
-- date, so nothing is lost.
--
-- No saved report, dashboard card or schedule uses page_count on INT (checked
-- before writing this), so unlike doc_count in 0103 there is nothing to repoint.
-- A PROD report still on it keeps its definition and stops resolving, same
-- contract as any other retired measure -- its owner rebuilds it on
-- pages_imported or pages_exported.
--
-- Disabled, not deleted: dbo.ReportingMetrics is read WHERE Enabled = 1, so this
-- is one UPDATE away from coming back and the definition stays on record.
--
-- Idempotent.

UPDATE dbo.ReportingMetrics
SET Enabled = 0
WHERE Code = 'page_count';
GO
