-- 0034_permission_sortingcode_and_pdbsuser_case.sql
-- 1) dbo.Permission.SortingCode: referenced by the admin permission APIs
--    (api_admin_permission_add/edit, api_admin_user_all_permissions) since the
--    April admin redesign, but the column was never migrated -> those routes 500.
-- 2) Normalize the one hand-inserted mixed-case assign code to the lowercase
--    convention the app checks (admin.py builds codes with .lower()).
-- Idempotent: guarded / naturally re-runnable. LOWER() makes the match
-- collation-proof (CI or CS).

IF COL_LENGTH('dbo.Permission', 'SortingCode') IS NULL
    ALTER TABLE dbo.Permission ADD SortingCode nvarchar(50) NULL;
GO

UPDATE dbo.Permission
SET Code = 'admin.assign.user.accessprofile.pdbsuser'
WHERE LOWER(Code) = 'admin.assign.user.accessprofile.pdbsuser';
GO
