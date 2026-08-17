-- 0054_backlog_history_snapshot_grainable.sql
-- REF #162: the Simple wizard's "over time" breakdown and the AI assistant's
-- date-token filters only offer/accept fields flagged `grainable` in the
-- source's ColumnsJSON (nx_lib/reporting/schema.py, ai_schema.py). 0053
-- registered SnapshotAt without that flag, so charting the backlog over time
-- wasn't actually reachable. Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"SnapshotAt","label":"Snapshot at","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"SourceCode","label":"Source","type":"string","filterable":true,"sortable":true},
       {"field":"ClientName","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"ProcessName","label":"Process","type":"string","filterable":true,"sortable":true},
       {"field":"BacklogCount","label":"Backlog count","type":"number","filterable":true,"sortable":true}]'
WHERE Code = 'backlog_history'
  AND ColumnsJSON NOT LIKE '%grainable%';
GO
