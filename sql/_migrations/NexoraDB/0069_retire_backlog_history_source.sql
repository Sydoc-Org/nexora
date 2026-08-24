-- 0069_retire_backlog_history_source.sql
-- Retire the standalone Backlog History reporting source (seeded 0053-0056,
-- 0065-0066, relabeled 0068): the anchored "Backlog" measure on the
-- docprocessing source (0067) supersedes it — combinable with imports/
-- exports, process-scoped, latest-per-bucket. Saved reports/dashboards
-- referencing the old source or its backlog_total metric are deleted
-- (owner-approved; they cannot run once the source is gone). The
-- dbo.BacklogHistory TABLE and its collector stay — the anchored measure
-- reads them directly. Idempotent.

-- 1) saved reports + dashboards referencing the retired source/metric
DELETE s FROM dbo.ReportShares s
JOIN dbo.Reports r ON r.ReportID = s.ReportID
WHERE r.DefinitionJSON LIKE '%backlog_history%' OR r.DefinitionJSON LIKE '%backlog_total%';
GO

DELETE s FROM dbo.ReportSchedules s
JOIN dbo.Reports r ON r.ReportID = s.ReportID
WHERE r.DefinitionJSON LIKE '%backlog_history%' OR r.DefinitionJSON LIKE '%backlog_total%';
GO

DELETE FROM dbo.Reports
WHERE DefinitionJSON LIKE '%backlog_history%' OR DefinitionJSON LIKE '%backlog_total%';
GO

-- 2) metric + source registry rows
DELETE FROM dbo.ReportingMetrics WHERE Code = 'backlog_total';
DELETE FROM dbo.ReportingSources WHERE Code = 'backlog_history';
GO

-- 3) the source permission (profile grants, user overrides, then the code)
DELETE app FROM dbo.AccessProfilePermission app
JOIN dbo.Permission p ON p.PermissionID = app.PermissionID
WHERE p.Code = 'reporting.source.backlog_history';

DELETE upo FROM dbo.UserPermissionOverride upo
JOIN dbo.Permission p ON p.PermissionID = upo.PermissionID
WHERE p.Code = 'reporting.source.backlog_history';

DELETE FROM dbo.Permission WHERE Code = 'reporting.source.backlog_history';
GO
