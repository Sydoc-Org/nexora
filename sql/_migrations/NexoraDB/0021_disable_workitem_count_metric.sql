-- 0021: consolidate count metrics - disable workitem_count.
-- Owner verified 2026-06-11 on PROD: COUNT(*), COUNT(WorkitemID),
-- COUNT(DISTINCT WorkItemID) and COUNT(Barcode) all return the same number
-- on the docprocessing Statistics tables (one row per workitem, no NULL ids),
-- so this metric always equals doc_count. Disabled rather than deleted:
-- reversible, and the workitem_id dimension field stays available.
UPDATE dbo.ReportingMetrics SET Enabled = 0 WHERE Code = 'workitem_count';
GO
