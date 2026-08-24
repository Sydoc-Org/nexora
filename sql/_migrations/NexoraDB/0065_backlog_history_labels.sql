-- 0065_backlog_history_labels.sql
-- Reporting usability: the backlog source's "Snapshot at" label confused
-- users ("Stand" is the familiar as-of term), and its ProcessName picker
-- showed bare Octo process names with no client. `labelWith` tells the
-- field_values endpoint to label each distinct ProcessName with its
-- ClientName companion ("privera.03_Invoice_New" style, matching the rest
-- of the app). Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"SnapshotAt","label":"Stand","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"SourceCode","label":"Source","type":"string","filterable":true,"sortable":true},
       {"field":"ClientName","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"ProcessName","label":"Process","type":"string","filterable":true,"sortable":true,"labelWith":"ClientName"},
       {"field":"BacklogCount","label":"Backlog count","type":"number","filterable":true,"sortable":true}]'
WHERE Code = 'backlog_history'
  AND ColumnsJSON NOT LIKE '%labelWith%';
GO
