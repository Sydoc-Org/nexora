-- 0025_ms02_praesidialdepartement_dashboard_process.sql
-- Register the MS02 client "Praesidialdepartement BS" as a dashboard process.
--
-- Two data rows (no DDL):
--  1. dbo.Permission: the dashboard process-filter permission. The dashboard
--     only recognises codes of the canonical shape
--     'dashboard.filter.process.<client>.<process>' (it parses the last two
--     dot-segments as <client>.<process>). An earlier manual insert used
--     'dashboard.filter.sydoc.praesidialdepartement_bs' -- MISSING the
--     '.process.' segment -- so the process never appeared in the filter.
--     Rename that row in place if present (preserves any grant on its
--     PermissionID via AccessProfilePermission / UserPermissionOverride),
--     otherwise insert the canonical code on a fresh environment.
--  2. dbo.Statconfig: map that process to MS02's batchtracking stats table
--     (ClientCode 'ms02' routes the dashboard stats to engine_ms02_stats_pg ->
--     public.batchtracking in the separate Praesidialdepartement_BS DB).
--
-- NOTE: this registers the permission code in the catalog; GRANTING it to an
-- access profile / user is an admin-UI action per environment (already done on
-- INT). Workitems-list visibility of MS02 needs a SEPARATE permission
-- 'workitems.filter.process.sydoc.praesidialdepartement_bs' (not added here).

IF EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'dashboard.filter.sydoc.praesidialdepartement_bs')
   AND NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'dashboard.filter.process.sydoc.praesidialdepartement_bs')
BEGIN
    UPDATE dbo.Permission
    SET Code = 'dashboard.filter.process.sydoc.praesidialdepartement_bs'
    WHERE Code = 'dashboard.filter.sydoc.praesidialdepartement_bs';
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'dashboard.filter.process.sydoc.praesidialdepartement_bs')
BEGIN
    INSERT INTO dbo.Permission (Code, Description)
    VALUES ('dashboard.filter.process.sydoc.praesidialdepartement_bs',
            'View Praesidialdepartement BS (MS02) dashboard process');
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Statconfig WHERE ProcessName = 'sydoc.praesidialdepartement_bs')
BEGIN
    INSERT INTO dbo.Statconfig (ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode)
    VALUES ('sydoc.praesidialdepartement_bs', 'public.batchtracking', 'datuminexport', 'datumimportiert', NULL, 'ms02');
END
GO
