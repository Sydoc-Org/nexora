-- 0093: the Mobscn tenant's pages as its users should see them (#257).
--
-- A Mobscn user gets Dashboard, Workitems and Prepared Documents inside the tenant group
-- (the global sidebar links are hidden for tenant-scoped users as of this change), with
-- proper labels/icons/active markers in LayoutJSON. The generated "PDBS Dossiers" list
-- page is taken out of the navigation: Status 'draft' keeps the row and its entity/field
-- descriptors for later, but the registry only serves 'active' pages, so the sidebar
-- entry and /t/ms02/sydoc.05_PDBS disappear.

INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'ms02', 'dashboard', 'custom', NULL,
       '{"endpoint": "dashboard", "label": "Dashboard", "icon": "fa-gauge-high", "active": "dashboard"}', 5, 'active'
WHERE NOT EXISTS (SELECT 1 FROM dbo.TenantPages WHERE TenantCode = 'ms02' AND PageKey = 'dashboard');
GO

UPDATE dbo.TenantPages
   SET LayoutJSON = '{"endpoint": "workitems_overview", "label": "Workitems", "icon": "fa-layer-group", "active": "workitems_overview"}'
 WHERE TenantCode = 'ms02' AND PageKey = 'workitems';
UPDATE dbo.TenantPages
   SET LayoutJSON = '{"endpoint": "prepared_documents", "label": "Prepared Documents", "icon": "fa-file-circle-check", "active": "prepared_documents"}'
 WHERE TenantCode = 'ms02' AND PageKey = 'prepared';
GO

UPDATE dbo.TenantPages
   SET Status = 'draft'
 WHERE TenantCode = 'ms02' AND PageKey = 'sydoc.05_PDBS' AND PageType = 'list';
GO
