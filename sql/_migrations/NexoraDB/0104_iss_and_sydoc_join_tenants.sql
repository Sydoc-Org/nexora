-- 0104: ISS joins the Generali tenant, sydoc AG joins the Sydoc tenant.
--
-- 0094 left sydoc AG (SYDC) and ISS (SSIX) outside any tenant. Since 0096 a tenant is a
-- branded portal and membership (Organizations.TenantCode) alone opens it, so both can be
-- seated where they work: ISS runs the Generali service and lives in that portal (its
-- profiles already hold tenant.generali.view -- harmless next to membership, left in
-- place); sydoc AG is the Sydoc tenant's own staff. A member lands on their tenant's
-- Dashboard/Workitems by default (0097/0098); sydoc staff with tenant.*.view grants keep
-- every tenant group plus the Global entries. Demo (DMEO) stays outside on purpose.

UPDATE dbo.Organizations SET TenantCode = 'generali'
 WHERE organizationcode = 'SSIX' AND TenantCode IS NULL;
GO

UPDATE dbo.Organizations SET TenantCode = 'sydoc'
 WHERE organizationcode = 'SYDC' AND TenantCode IS NULL;
GO
