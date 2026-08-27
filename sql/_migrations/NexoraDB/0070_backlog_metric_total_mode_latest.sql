-- 0070_backlog_metric_total_mode_latest.sql
-- The anchored "Backlog" measure (0067) is a LEVEL, not an event count: the
-- Simple tab's Total card must show the newest bucket's value, not the sum of
-- every snapshot in the range (0056 gave the retired backlog_total metric the
-- same 'latest' TotalMode; 0067 forgot to carry it over). Idempotent.
UPDATE dbo.ReportingMetrics
   SET TotalMode = 'latest'
 WHERE Code = 'backlog' AND ISNULL(TotalMode, 'sum') <> 'latest';
GO
