-- 0056_reporting_metrics_total_mode.sql
-- #178: how a metric's zero-dimension "grand total" is computed.
--   'sum'    = aggregate over all matching rows (default, unchanged)
--   'latest' = aggregate only the rows of the latest date bucket — for
--              point-in-time snapshot series (backlog), where summing
--              snapshots across time is meaningless.
-- Idempotent.
IF COL_LENGTH('dbo.ReportingMetrics', 'TotalMode') IS NULL
BEGIN
    ALTER TABLE dbo.ReportingMetrics
        ADD TotalMode NVARCHAR(16) NOT NULL
            CONSTRAINT DF_ReportingMetrics_TotalMode DEFAULT 'sum'
            CONSTRAINT CK_ReportingMetrics_TotalMode CHECK (TotalMode IN ('sum', 'latest'));
END
GO
UPDATE dbo.ReportingMetrics SET TotalMode = 'latest' WHERE Code = 'backlog_total';
GO
