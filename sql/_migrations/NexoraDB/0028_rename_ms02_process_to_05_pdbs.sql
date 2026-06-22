-- 0028_rename_ms02_process_to_05_pdbs.sql
-- The MS02 client's Octo process was renamed from 'praesidialdepartement_bs' to
-- '05_PDBS'. Migrations 0025/0026 registered the dashboard + workitems
-- process-filter permissions under the old process segment, and 0025 seeded the
-- Statconfig row under the old ProcessName. nexora keys both off the live Octo
-- process Name (t_Processes.Name = '05_PDBS', ClientName = 'sydoc'), so those
-- rows must be renamed to match or the process stops being filterable / its
-- dashboard stats stop routing.
--
-- Data only (no DDL). Three in-place renames (NOT re-inserts) so existing grants
-- on each PermissionID (via AccessProfilePermission / UserPermissionOverride)
-- survive. Already applied manually on INT; this records it so STAGING/PROD get
-- it too. Idempotent: each rename runs only when the OLD code/name still exists
-- and the NEW one does not, so re-applying on an already-migrated environment is
-- a clean no-op (and avoids any unique-key clash).

-- 1. Dashboard process-filter permission (companion to 0025).
IF EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'dashboard.filter.process.sydoc.praesidialdepartement_bs')
   AND NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'dashboard.filter.process.sydoc.05_PDBS')
BEGIN
    UPDATE dbo.Permission
    SET Code = 'dashboard.filter.process.sydoc.05_PDBS'
    WHERE Code = 'dashboard.filter.process.sydoc.praesidialdepartement_bs';
END
GO

-- 2. Workitems process-filter permission (companion to 0026).
IF EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'workitems.filter.process.sydoc.praesidialdepartement_bs')
   AND NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'workitems.filter.process.sydoc.05_PDBS')
BEGIN
    UPDATE dbo.Permission
    SET Code = 'workitems.filter.process.sydoc.05_PDBS'
    WHERE Code = 'workitems.filter.process.sydoc.praesidialdepartement_bs';
END
GO

-- 3. Dashboard-stats routing row (seeded in 0025). ProcessName matches the
--    '<client>.<process>' key the dashboard builds from the live Octo process.
IF EXISTS (SELECT 1 FROM dbo.Statconfig WHERE ProcessName = 'sydoc.praesidialdepartement_bs')
   AND NOT EXISTS (SELECT 1 FROM dbo.Statconfig WHERE ProcessName = 'sydoc.05_PDBS')
BEGIN
    UPDATE dbo.Statconfig
    SET ProcessName = 'sydoc.05_PDBS'
    WHERE ProcessName = 'sydoc.praesidialdepartement_bs';
END
GO
