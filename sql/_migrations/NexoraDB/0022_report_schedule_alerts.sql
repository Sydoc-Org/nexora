-- 0022_report_schedule_alerts.sql
-- Alert-only scheduled reports: a schedule may carry a threshold condition
-- (AlertOp + AlertThreshold). The runner (ops/run_scheduled_reports.py) only
-- mails when the report's grand total (or row count for non-metric
-- definitions) satisfies it. NULL AlertOp = always send (the default; fully
-- back-compatible). Ops (gt/gte/lt/lte) are validated in the app layer
-- (nx_lib/reporting/schedule.py ALERT_OPS) -- no DB CHECK on purpose, so the
-- TEST schema mirror stays equivalent. Idempotent.

IF COL_LENGTH(N'dbo.ReportSchedules', N'AlertOp') IS NULL
    ALTER TABLE dbo.ReportSchedules ADD AlertOp NVARCHAR(8) NULL;
GO

IF COL_LENGTH(N'dbo.ReportSchedules', N'AlertThreshold') IS NULL
    ALTER TABLE dbo.ReportSchedules ADD AlertThreshold FLOAT NULL;
GO
