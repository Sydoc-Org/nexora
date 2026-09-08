-- 0096: a tenant is a branded portal, not a data connection.
--
-- Decision 2026-09-03: Tenant = the set of organizations that share one navigation,
-- look and permission group. Where data lives is a property of the thing that reads
-- it -- a process source (ProcessSources.ClientCode, already its PK) or a generated
-- entity (a table lives in exactly one database). So:
--   * TenantEntities gains ClientCode, backfilled from the tenant it belongs to;
--   * Organizations.ClientCode (0090) and Tenants.ClientCode (0084) go -- both were
--     denormalized copies that agreed with the sources in every row;
--   * Tenants.OrganizationCode, the pre-0090 single-org pointer, goes with them.
-- Membership (Organizations.TenantCode) now also grants sidebar visibility; the
-- tenant.<code>.view permission survives only as the grant for non-members.

IF COL_LENGTH('dbo.TenantEntities', 'ClientCode') IS NULL
    ALTER TABLE dbo.TenantEntities ADD ClientCode NVARCHAR(50) NULL;
GO
UPDATE e
   SET e.ClientCode = t.ClientCode
  FROM dbo.TenantEntities e
  JOIN dbo.Tenants t ON t.TenantCode = e.TenantCode
 WHERE e.ClientCode IS NULL
   AND COL_LENGTH('dbo.Tenants', 'ClientCode') IS NOT NULL;
GO
IF EXISTS (SELECT 1 FROM dbo.TenantEntities WHERE ClientCode IS NULL)
    THROW 50096, '0096: TenantEntities rows without a ClientCode after backfill', 1;
GO
ALTER TABLE dbo.TenantEntities ALTER COLUMN ClientCode NVARCHAR(50) NOT NULL;
GO
IF OBJECT_ID('dbo.FK_TenantEntities_Clients', 'F') IS NULL
    ALTER TABLE dbo.TenantEntities ADD CONSTRAINT FK_TenantEntities_Clients
        FOREIGN KEY (ClientCode) REFERENCES dbo.Clients (ClientCode);
GO

IF OBJECT_ID('dbo.FK_Organizations_Clients', 'F') IS NOT NULL
    ALTER TABLE dbo.Organizations DROP CONSTRAINT FK_Organizations_Clients;
GO
IF COL_LENGTH('dbo.Organizations', 'ClientCode') IS NOT NULL
    ALTER TABLE dbo.Organizations DROP COLUMN ClientCode;
GO

IF OBJECT_ID('dbo.FK_Tenants_Clients', 'F') IS NOT NULL
    ALTER TABLE dbo.Tenants DROP CONSTRAINT FK_Tenants_Clients;
GO
IF COL_LENGTH('dbo.Tenants', 'ClientCode') IS NOT NULL
    ALTER TABLE dbo.Tenants DROP COLUMN ClientCode;
GO
IF OBJECT_ID('dbo.FK_Tenants_Organizations', 'F') IS NOT NULL
    ALTER TABLE dbo.Tenants DROP CONSTRAINT FK_Tenants_Organizations;
GO
IF COL_LENGTH('dbo.Tenants', 'OrganizationCode') IS NOT NULL
    ALTER TABLE dbo.Tenants DROP COLUMN OrganizationCode;
GO
