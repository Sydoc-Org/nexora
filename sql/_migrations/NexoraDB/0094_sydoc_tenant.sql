-- 0094: the Sydoc tenant -- the customers sydoc hosts on the shared default runtime (#257).
--
-- ElektroMaterial (LKTR), Privera (PRVR) and Compass join a new tenant 'sydoc'. Compass had
-- process sources (compass.01_Invoice_SAP) and a profile (compassUser) but no organization
-- row; it gets one (CMPS) and its source is assigned to it. The tenant carries the same
-- three mounted pages as Mobscn (Dashboard, Workitems, Prepared Documents), so its users
-- -- tenant-scoped since 0093 -- keep reaching what they use today.
--
-- Tenants.OrganizationCode is the pre-0090 "the one organization" pointer; a tenant with
-- several organizations has no single answer, so the column becomes nullable here and the
-- new tenant leaves it NULL. Organizations.TenantCode is the relation that counts.
--
-- Not done here, on purpose: compassUser stays a global profile because a DMEO user
-- (invite.demo) holds it -- binding it to CMPS would strand that user; and sydoc AG (SYDC),
-- ISS (SSIX) and demo (DMEO) stay outside any tenant.

ALTER TABLE dbo.Tenants ALTER COLUMN OrganizationCode NVARCHAR(5) NULL;
GO

INSERT INTO dbo.Organizations (organizationcode, Organization, ClientCode)
SELECT 'CMPS', 'Compass', 'default'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Organizations WHERE organizationcode = 'CMPS');
GO

INSERT INTO dbo.Tenants (TenantCode, DisplayName, OrganizationCode, ClientCode, IsActive)
SELECT 'sydoc', 'Sydoc', NULL, 'default', 1
WHERE NOT EXISTS (SELECT 1 FROM dbo.Tenants WHERE TenantCode = 'sydoc');
GO

UPDATE dbo.Organizations SET TenantCode = 'sydoc'
 WHERE organizationcode IN ('LKTR', 'PRVR', 'CMPS') AND TenantCode IS NULL;
GO

UPDATE dbo.ProcessSources SET OrganizationCode = 'CMPS'
 WHERE ClientCode = 'default' AND ProcessName LIKE 'compass.%' AND OrganizationCode IS NULL;
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.sydoc.view', 'View sydoc tenant records'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.sydoc.view');
INSERT INTO dbo.Permission (Code, Description)
SELECT 'tenant.sydoc.edit', 'Edit sydoc tenant records'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'tenant.sydoc.edit');
GO

-- tenant.sydoc.view: every profile bound to a member organization, plus globalAdmin so the
-- platform admins see the group. Nobody gets .edit.
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, tv.PermissionID, 'A'
  FROM dbo.AccessProfile ap
  JOIN dbo.Permission tv ON tv.Code = 'tenant.sydoc.view'
 WHERE (ap.OrganizationCode IN ('LKTR', 'PRVR', 'CMPS') OR ap.Name = 'globalAdmin')
   AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = tv.PermissionID
       );
GO

INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'sydoc', v.PageKey, 'custom', NULL, v.LayoutJSON, v.SortOrder, 'active'
FROM (VALUES
    ('dashboard', '{"endpoint": "dashboard",          "label": "Dashboard",          "icon": "fa-gauge-high",        "active": "dashboard"}',          10),
    ('workitems', '{"endpoint": "workitems_overview", "label": "Workitems",          "icon": "fa-layer-group",       "active": "workitems_overview"}', 20),
    ('prepared',  '{"endpoint": "prepared_documents", "label": "Prepared Documents", "icon": "fa-file-circle-check", "active": "prepared_documents"}', 30)
) AS v (PageKey, LayoutJSON, SortOrder)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.TenantPages tp WHERE tp.TenantCode = 'sydoc' AND tp.PageKey = v.PageKey
);
GO
