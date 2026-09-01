-- 0085: seed the ms02 pilot tenant from the mapping tables (tenant-kernel-ms02-pilot, Task 8).
-- Migration number: the plan's own Task 8 text names "0084", but 0084 was already claimed by
-- 0084_tenant_box_tables.sql (Task 1) on this branch by the time this file was authored;
-- verified free via `python scripts/db-migrate.py --env INT --dry-run` before creating it.
--
-- dbo.Organizations gap (owner action #1, resolved here): the plan assumes an
-- `organizationcode` row for the MS02 customer already exists in dbo.Organizations and this
-- migration only has to pick it. Checked live INT
-- (`SELECT organizationcode, Organization FROM dbo.Organizations`): the table holds only
-- DMEO / LKTR / PRVR / SSIX / SYDC -- no row for MS02's customer, and dbo.Clients.ms02 carries
-- no OrganizationCode column to fall back on. There is therefore no existing row to "pick";
-- this migration INSERTS the missing row rather than resolving to one. The code and name come
-- from this repo's own history, not a guess: migrations 0025/0028's comments name the client
-- "Praesidialdepartement BS" / Octo process "05_PDBS", and both configured MS02 Postgres
-- engines (engine_ms02_stats_pg, engine_ms02_docfields_pg) point at a live database literally
-- named Praesidialdepartement_BS (confirmed by connecting to both, 2026-09-01). 'PDBS' matches
-- the existing 4-letter-code convention (DMEO/LKTR/PRVR/SSIX/SYDC) and this client's own
-- established abbreviation ("05_PDBS").
--
-- EngineRole probe (owner action #2, resolved here): `SELECT TOP 3 * FROM dbo.ProcessSources
-- WHERE ClientCode = 'ms02'` on INT returns exactly one row -- ProcessName
-- 'sydoc.05_PDBS', TableName public."DossierStatistik", WorkitemColumn 'WorkItemID'.
-- Probed both `engine_ms02_stats_pg` and `engine_ms02_docfields_pg` with
-- `SELECT current_database()` plus `SELECT 1 FROM public."DossierStatistik" LIMIT 1`: both
-- engines resolve to the SAME physical database (Praesidialdepartement_BS, same Azure Postgres
-- host) and both see the table identically -- there is no divergence to route on. Per the
-- brief's stated default when the probe finds the engines equivalent, EngineRole is seeded as
-- 'docfields'.
--
-- ProcessFieldMappings for ms02 (6 rows, all under 'sydoc.05_PDBS') all resolve against
-- dbo.FieldLabels with no missing FieldKey. SemanticRole is heuristic from ColumnType:
-- 'character varying' -> 'text' (archiveboxno, batchname, docbarcode, pid),
-- 'bigint' -> 'count' (dossierpositioninbatch, pagecount). No date-ish columns present.
--
-- tenant.ms02.view / tenant.ms02.edit are seeded granted to nobody (the brief's default; the
-- owner did not ask for a workitems.view-based grant) -- an operator grants them via
-- /admin/access-control once the pilot is ready for real users.

-- dbo.Organizations: new PDBS row (see rationale above) -- must precede the Tenants insert,
-- which FKs OrganizationCode -> dbo.Organizations.organizationcode.
INSERT INTO dbo.Organizations (organizationcode, Organization)
SELECT 'PDBS', N'Praesidialdepartement Basel-Stadt'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Organizations WHERE organizationcode = 'PDBS');
GO

-- dbo.Tenants: the ms02 pilot tenant row.
INSERT INTO dbo.Tenants (TenantCode, DisplayName, OrganizationCode, ClientCode, IsActive)
SELECT 'ms02', 'MS02', 'PDBS', 'ms02', 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.Tenants WHERE TenantCode = 'ms02');
GO

-- dbo.Permission: tenant.ms02.view / .edit, granted to nobody by default.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.ms02.view', 'View the MS02 pilot tenant data pages'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.ms02.view');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.ms02.edit', 'Edit the MS02 pilot tenant data pages'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.ms02.edit');
GO

-- dbo.TenantEntities: one row per ms02 ProcessSources row with a TableName (currently 1:
-- sydoc.05_PDBS / public."DossierStatistik"). IdColumn = WorkitemColumn; LabelEn adjusted to a
-- readable name rather than the raw dotted ProcessName.
INSERT INTO dbo.TenantEntities (TenantCode, EntityKey, SourceObject, Kind, EngineRole, IdColumn, LabelEn, SortOrder, Status)
SELECT DISTINCT 'ms02', ps.ProcessName, ps.TableName, 'documents', 'docfields', ps.WorkitemColumn,
       'PDBS Dossiers', 100, 'active'
FROM dbo.ProcessSources ps
WHERE ps.ClientCode = 'ms02'
  AND ps.TableName IS NOT NULL
  AND NOT EXISTS (
        SELECT 1 FROM dbo.TenantEntities te
        WHERE te.TenantCode = 'ms02' AND te.EntityKey = ps.ProcessName
  );
GO

-- dbo.TenantFields: ms02 ProcessFieldMappings rows, joined to FieldLabels for the four locale
-- labels. SemanticRole heuristic: int-ish ColumnType -> 'count', date-ish -> 'date', else 'text'.
INSERT INTO dbo.TenantFields (TenantCode, EntityKey, ColumnName, SemanticRole, LabelEn, LabelDe, LabelFr, LabelIt, Status)
SELECT 'ms02', pfm.ProcessName, pfm.ColumnName,
       CASE
           WHEN LOWER(pfm.ColumnType) IN ('int', 'bigint', 'integer', 'smallint') THEN 'count'
           WHEN LOWER(pfm.ColumnType) IN ('date', 'timestamp') THEN 'date'
           ELSE 'text'
       END,
       fl.EnglishLabel, fl.GermanLabel, fl.FrenchLabel, fl.ItalianLabel, 'active'
FROM dbo.ProcessFieldMappings pfm
JOIN dbo.FieldLabels fl ON fl.FieldKey = pfm.FieldKey
WHERE pfm.ClientCode = 'ms02'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.TenantFields tf
        WHERE tf.TenantCode = 'ms02' AND tf.EntityKey = pfm.ProcessName AND tf.ColumnName = pfm.ColumnName
  );
GO

-- dbo.TenantPages: one generated list page per seeded entity, plus the two custom mounts for
-- the shared workitems viewer and the prepared-documents register.
INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'ms02', te.EntityKey, 'list', te.EntityKey, NULL, 100, 'active'
FROM dbo.TenantEntities te
WHERE te.TenantCode = 'ms02'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.TenantPages tp
        WHERE tp.TenantCode = 'ms02' AND tp.PageKey = te.EntityKey
  );
GO

INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'ms02', 'workitems', 'custom', NULL, '{"endpoint": "workitems_overview"}', 10, 'active'
WHERE NOT EXISTS (SELECT 1 FROM dbo.TenantPages WHERE TenantCode = 'ms02' AND PageKey = 'workitems');
GO

INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'ms02', 'prepared', 'custom', NULL, '{"endpoint": "prepared_documents"}', 20, 'active'
WHERE NOT EXISTS (SELECT 1 FROM dbo.TenantPages WHERE TenantCode = 'ms02' AND PageKey = 'prepared');
GO
