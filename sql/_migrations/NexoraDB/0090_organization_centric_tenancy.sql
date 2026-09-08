-- 0090: organization-centric tenancy (#257).
--
-- The organization becomes the hub: it belongs to a tenant, and it owns its users,
-- its data connection, its process configurations and its access profiles. Four
-- nullable FK columns, all backfilled from relations the data already follows by
-- convention, so nothing existing changes meaning:
--
--   Organizations.TenantCode        <- Tenants.OrganizationCode (the arrow flips)
--   Organizations.ClientCode        <- the tenant's connection, else 'default'
--   ProcessSources.OrganizationCode <- the tenant whose connection serves it, else the
--                                      <customer>.<process> name prefix
--   AccessProfile.OrganizationCode  <- the profile-name prefix (priveraUser -> Privera);
--                                      NULL = global profile (globalAdmin, ...)
--
-- Tenants.OrganizationCode stays for now: the tenant registry (nx_lib/tenant/registry.py)
-- and the 0085 seed still read it. Once Organizations.TenantCode is the only reader, a
-- later migration drops it -- immutable-migration rule, so not here.
--
-- Migration number: 0086-0088 are claimed by #238, 0089 by #255; verified free with
-- `python scripts/db-migrate.py --env INT --dry-run`.

-- ---------------------------------------------------------------- Organizations --
IF COL_LENGTH('dbo.Organizations', 'TenantCode') IS NULL
    ALTER TABLE dbo.Organizations ADD TenantCode NVARCHAR(50) NULL;
GO
IF COL_LENGTH('dbo.Organizations', 'ClientCode') IS NULL
    ALTER TABLE dbo.Organizations ADD ClientCode NVARCHAR(50) NULL;
GO
IF OBJECT_ID('dbo.FK_Organizations_Tenants', 'F') IS NULL
    ALTER TABLE dbo.Organizations ADD CONSTRAINT FK_Organizations_Tenants
        FOREIGN KEY (TenantCode) REFERENCES dbo.Tenants (TenantCode);
GO
IF OBJECT_ID('dbo.FK_Organizations_Clients', 'F') IS NULL
    ALTER TABLE dbo.Organizations ADD CONSTRAINT FK_Organizations_Clients
        FOREIGN KEY (ClientCode) REFERENCES dbo.Clients (ClientCode);
GO

-- A tenant's organization inherits the tenant and its connection.
UPDATE o
   SET o.TenantCode = t.TenantCode,
       o.ClientCode = COALESCE(o.ClientCode, t.ClientCode)
  FROM dbo.Organizations o
  JOIN dbo.Tenants t ON t.OrganizationCode = o.organizationcode
 WHERE o.TenantCode IS NULL;
GO
-- Everyone else rides the shared default connection (the pre-0079 world, made explicit).
UPDATE dbo.Organizations
   SET ClientCode = 'default'
 WHERE ClientCode IS NULL
   AND EXISTS (SELECT 1 FROM dbo.Clients WHERE ClientCode = 'default');
GO

-- --------------------------------------------------------------- ProcessSources --
IF COL_LENGTH('dbo.ProcessSources', 'OrganizationCode') IS NULL
    ALTER TABLE dbo.ProcessSources ADD OrganizationCode NVARCHAR(5) NULL;
GO
IF OBJECT_ID('dbo.FK_ProcessSources_Organizations', 'F') IS NULL
    ALTER TABLE dbo.ProcessSources ADD CONSTRAINT FK_ProcessSources_Organizations
        FOREIGN KEY (OrganizationCode) REFERENCES dbo.Organizations (organizationcode);
GO

-- 1. A source on a tenant's own connection belongs to that tenant's organization.
UPDATE ps
   SET ps.OrganizationCode = t.OrganizationCode
  FROM dbo.ProcessSources ps
  JOIN dbo.Tenants t ON t.ClientCode = ps.ClientCode
 WHERE ps.OrganizationCode IS NULL
   AND ps.ClientCode <> 'default';
GO
-- 2. Otherwise the <customer> half of the process name, matched against the
--    organization's name or code (privera.02_Posteingang -> Privera; compass.* has
--    no organization row and stays NULL -- visible on /admin/tenants, fix by hand).
UPDATE ps
   SET ps.OrganizationCode = o.organizationcode
  FROM dbo.ProcessSources ps
  JOIN dbo.Organizations o
    ON LOWER(LEFT(ps.ProcessName, CHARINDEX('.', ps.ProcessName + '.') - 1))
       IN (LOWER(o.Organization), LOWER(o.organizationcode))
 WHERE ps.OrganizationCode IS NULL;
GO

-- ---------------------------------------------------------------- AccessProfile --
IF COL_LENGTH('dbo.AccessProfile', 'OrganizationCode') IS NULL
    ALTER TABLE dbo.AccessProfile ADD OrganizationCode NVARCHAR(5) NULL;
GO
IF OBJECT_ID('dbo.FK_AccessProfile_Organizations', 'F') IS NULL
    ALTER TABLE dbo.AccessProfile ADD CONSTRAINT FK_AccessProfile_Organizations
        FOREIGN KEY (OrganizationCode) REFERENCES dbo.Organizations (organizationcode);
GO

-- Per-customer profiles are named after the customer today (priveraUser,
-- issSupervisor, pdbsUser, elektromaterialUser). Bind them; the platform-wide
-- profiles stay NULL = global and remain assignable to anyone.
UPDATE ap
   SET ap.OrganizationCode = o.organizationcode
  FROM dbo.AccessProfile ap
  JOIN dbo.Organizations o
    ON LOWER(ap.Name) LIKE LOWER(o.Organization) + '%'
    OR LOWER(ap.Name) LIKE LOWER(o.organizationcode) + '%'
 WHERE ap.OrganizationCode IS NULL
   AND ap.Name NOT IN ('globalAdmin', 'enterpriseAdmin', 'nexoraSupervisor');
GO
