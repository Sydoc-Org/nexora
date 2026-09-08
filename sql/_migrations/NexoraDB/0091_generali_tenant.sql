-- 0091: Generali becomes a tenant (#257 follow-up).
--
-- The tenant *shell*: a data connection row for the Generali database, an organization,
-- the tenant, its permissions, and one 'custom' page per existing Generali page so the
-- sidebar group comes from the tenant registry instead of the hardcoded block that
-- templates/_header.html carried until now. The pages themselves, their CRUD code and
-- the 46 generali.* permissions are untouched -- folding those into tenant.generali.*
-- is #238's job. Everything here is idempotent.
--
-- Migration number: 0090 is #257's organization-centric model; verified free with
-- `python scripts/db-migrate.py --env INT --dry-run`.

-- 1. Data connection. No Octo domain: this is a data-only connection, which
--    nx_lib/clients.py accepts as of this change (it used to skip domain-less rows).
INSERT INTO dbo.Clients (ClientCode, DisplayName, Dialect, RuntimeEngineKey, IsActive)
SELECT 'generali', 'Generali', 'tsql', 'engine_generali_db', 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.Clients WHERE ClientCode = 'generali');
GO

-- 2. Organization. The three-letter shape follows DMEO/LKTR/PRVR/SSIX/SYDC.
INSERT INTO dbo.Organizations (organizationcode, Organization, ClientCode)
SELECT 'GNRL', 'Generali', 'generali'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Organizations WHERE organizationcode = 'GNRL');
GO

-- 3. Tenant. Tenants.OrganizationCode is the pre-0090 pointer and still NOT NULL;
--    Organizations.TenantCode below is the one the overview reads.
INSERT INTO dbo.Tenants (TenantCode, DisplayName, OrganizationCode, ClientCode, IsActive)
SELECT 'generali', 'Generali', 'GNRL', 'generali', 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.Tenants WHERE TenantCode = 'generali');
GO
UPDATE dbo.Organizations SET TenantCode = 'generali'
 WHERE organizationcode = 'GNRL' AND TenantCode IS NULL;
GO

-- 4. Permissions (same shape nx_lib/tenant/registry.py::provision_tenant_permissions
--    writes), then tenant.generali.view for everyone who already reaches a Generali
--    page today -- via a profile grant or a personal override -- so the sidebar group
--    does not vanish for them. Nobody gets .edit.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.generali.view', 'View generali tenant records'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.generali.view');
INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.generali.edit', 'Edit generali tenant records'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.generali.edit');
GO
-- (The grant step that stood here matched nothing -- see 0092, which redoes it --
--  and read AccessProfilePermission.Effect, a column 0086 (#238) drops. On PROD
--  0086 runs first, so the step is gone rather than broken. Edited after INT
--  applied it; checksum re-blessed. See docs/howto/db-migrations.md.)

-- 5. Pages: one 'custom' mount per existing Generali page, in the sidebar's old order.
--    LayoutJSON carries endpoint + label + icon + the active_page value the page sets,
--    which nx_lib/views/tenant.py::_tenant_nav_page reads as of this change.
INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'generali', v.PageKey, 'custom', NULL, v.LayoutJSON, v.SortOrder, 'active'
FROM (VALUES
    ('dashboard',           '{"endpoint": "generali_evaluation",          "label": "Dashboard",           "icon": "fa-chart-line",       "active": "generali_dashboard"}',           10),
    ('documents',           '{"endpoint": "generali_documents",           "label": "Document List",       "icon": "fa-table-list",       "active": "generali_documents"}',           20),
    ('reporting',           '{"endpoint": "generali_reporting",           "label": "Reporting",           "icon": "fa-clipboard-list",   "active": "generali_reporting"}',           30),
    ('additional-services', '{"endpoint": "generali_additional_services", "label": "Additional Services", "icon": "fa-clock",            "active": "generali_additionalservices"}', 40),
    ('base-services',       '{"endpoint": "generali_base_services",       "label": "Base Services",       "icon": "fa-inbox",            "active": "generali_baseservices"}',        50),
    ('project-management',  '{"endpoint": "generali_project_management",  "label": "Project Management",  "icon": "fa-diagram-project",  "active": "generali_projectmanagement"}',   60),
    ('pdqm',                '{"endpoint": "generali_pdqm",                "label": "PDQM",                "icon": "fa-file-lines",       "active": "generali_pdqm"}',                70),
    ('import-status',       '{"endpoint": "generali_import_status",       "label": "Data Import Status",  "icon": "fa-database",         "active": "generali_importstatus"}',        80)
) AS v (PageKey, LayoutJSON, SortOrder)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.TenantPages tp WHERE tp.TenantCode = 'generali' AND tp.PageKey = v.PageKey
);
GO
