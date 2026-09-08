-- 0122: the Sydoc tenant never gets Prepared Documents (#257 follow-up).
--
-- 0094 copied Mobscn's three tenant pages (Dashboard, Workitems, Prepared Documents) onto
-- the new 'sydoc' tenant, but Prepared Documents is a hard MS02-only route --
-- prepared_documents() raises PermissionDenied for any non-MS02 client regardless of
-- permission grants (nx_lib/views/workitems.py). Every sydoc-tenant member (ElektroMaterial,
-- Privera, Compass, sydoc AG) would see the link and have it always fail. INT already had
-- the row removed by hand; this migration makes that the checked-in state so a fresh DB
-- or PROD's first run of 0094 doesn't recreate it.

DELETE FROM dbo.TenantPages WHERE TenantCode = 'sydoc' AND PageKey = 'prepared';
GO
