-- 0053_seed_backlog_history_reporting_source.sql
-- REF #162: surface ops/backlog_history's StatisticsDB.dbo.BacklogHistory
-- (30-min C+A backlog snapshots, see #161) on the Reporting page via the
-- generic 'table' provider — no bespoke code. A canonical metric is included
-- so the Simple wizard and the AI assistant both surface it (a source with
-- no registered metric is told to the AI as "cannot aggregate" and the
-- wizard has no measure to offer). Idempotent.

-- 1) permission
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.source.backlog_history', 'Reporting: use the Backlog History source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.source.backlog_history');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.source.backlog_history'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- 2) source
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'backlog_history')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'backlog_history', 'curated', 'Backlog History',
    'reporting.source.backlog_history', 'statistics', 'table', 'dbo.BacklogHistory',
    N'[{"field":"SnapshotAt","label":"Snapshot at","type":"datetime","filterable":true,"sortable":true},
       {"field":"SourceCode","label":"Source","type":"string","filterable":true,"sortable":true},
       {"field":"ClientName","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"ProcessName","label":"Process","type":"string","filterable":true,"sortable":true},
       {"field":"BacklogCount","label":"Backlog count","type":"number","filterable":true,"sortable":true}]',
    1, 40);
GO

-- 3) canonical metric
INSERT INTO dbo.ReportingMetrics (Code, SourceId, Label, Aggregation, BaseField, Description, Format, SortOrder)
SELECT 'backlog_total', 'backlog_history', 'Backlog', 'sum', 'BacklogCount',
       'Sum of backlog counts across matching snapshots', 'int', 40
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'backlog_total');
GO
