-- 0066_backlog_history_grant_scoped.sql
-- The backlog snapshot collector writes a row for EVERY process in Octo's
-- t_Processes, so the wizard's process picker offered processes nobody has
-- configured or wants to report on. `grantScoped` tells field_values to keep
-- only values whose client.process label is in the caller's
-- reporting.scope.process.* grants — the same list the rest of the app shows.
-- Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"SnapshotAt","label":"Stand","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"SourceCode","label":"Source","type":"string","filterable":true,"sortable":true},
       {"field":"ClientName","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"ProcessName","label":"Process","type":"string","filterable":true,"sortable":true,"labelWith":"ClientName","grantScoped":true},
       {"field":"BacklogCount","label":"Backlog count","type":"number","filterable":true,"sortable":true}]'
WHERE Code = 'backlog_history'
  AND ColumnsJSON NOT LIKE '%grantScoped%';
GO
