-- 0011_seed_generali_workitems_sources.sql
-- Two curated reporting sources registered through the registry (migration 0010)
-- using the generic 'table' provider — no bespoke code:
--   * generali_pdqm  -> Generali dbo.PDQMReport      (engine 'generali')
--   * workitems      -> Octopus  dbo.t_Documents     (engine 'octopus')
-- Each gets its own grantable permission, seeded to admin.view profiles. The
-- column catalogs below come from the live INT schema; an admin can adjust the
-- exposed columns / base object later via /reporting/sources. Idempotent.

-- 1) permissions
INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    ('reporting.source.generali.pdqm', 'Reporting: use the Generali PDQM Report source'),
    ('reporting.source.workitems',     'Reporting: use the Workitems (Octopus) source')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('reporting.source.generali.pdqm', 'reporting.source.workitems')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- 2) Generali PDQM Report source
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_pdqm')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_pdqm', 'curated', 'Generali — PDQM Report',
    'reporting.source.generali.pdqm', 'generali', 'table', 'dbo.PDQMReport',
    N'[{"field":"ForDate","label":"Date","type":"date","filterable":true,"sortable":true},
       {"field":"ParentCategory","label":"Parent category","type":"string","filterable":true,"sortable":true},
       {"field":"ParentSubCategory","label":"Parent subcategory","type":"string","filterable":true,"sortable":true},
       {"field":"SubCategory","label":"Subcategory","type":"string","filterable":true,"sortable":true},
       {"field":"Quantity","label":"Quantity","type":"number","filterable":true,"sortable":true},
       {"field":"UserID","label":"User ID","type":"number","filterable":true,"sortable":true},
       {"field":"RecordDateTime","label":"Recorded at","type":"datetime","filterable":true,"sortable":true}]',
    1, 20);
GO

-- 3) Workitems (Octopus documents) source. The binary Data column is intentionally
--    not exposed.
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'workitems')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'workitems', 'curated', 'Workitems (Octopus)',
    'reporting.source.workitems', 'octopus', 'table', 'dbo.t_Documents',
    N'[{"field":"WorkItemIdentifier","label":"Workitem ID","type":"string","filterable":true,"sortable":true},
       {"field":"DocumentName","label":"Document name","type":"string","filterable":true,"sortable":true},
       {"field":"DocumentRevision","label":"Revision","type":"number","filterable":true,"sortable":true},
       {"field":"ID","label":"Document ID","type":"string","filterable":true,"sortable":true},
       {"field":"ParentDocumentID","label":"Parent document ID","type":"string","filterable":true,"sortable":true}]',
    1, 30);
GO
