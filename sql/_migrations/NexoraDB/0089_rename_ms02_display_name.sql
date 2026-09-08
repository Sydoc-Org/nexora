-- 0089: the ms02 runtime source and tenant are labelled "Mobscn" in the UI (#255).
--
-- Display names only. The ClientCode / TenantCode stays 'ms02' -- it is the PK referenced by
-- dbo.ProcessSources, dbo.ProcessFieldMappings, dbo.WorkitemSourceCache and dbo.Tenants, it
-- names the MS02_* env keys, and it is baked into the tenant.ms02.view / .edit permission
-- codes. Renaming the code would strand all of those; renaming the label costs nothing.
--
-- Migration number: 0086-0088 are claimed by the (unmerged) permission-structure plan
-- (docs/superpowers/plans/2026-09-01-permission-structure-rename-grid.md), so this takes 0089.
-- Verified free against INT with `python scripts/db-migrate.py --env INT --dry-run`.

UPDATE dbo.Clients
   SET DisplayName = 'Mobscn'
 WHERE ClientCode = 'ms02'
   AND DisplayName <> 'Mobscn';
GO

-- dbo.Tenants only exists from 0084 onward; guard so this migration is safe on a database
-- where the tenant kernel has not been applied yet.
IF OBJECT_ID('dbo.Tenants', 'U') IS NOT NULL
BEGIN
    UPDATE dbo.Tenants
       SET DisplayName = 'Mobscn'
     WHERE TenantCode = 'ms02'
       AND DisplayName <> 'Mobscn';
END
GO
