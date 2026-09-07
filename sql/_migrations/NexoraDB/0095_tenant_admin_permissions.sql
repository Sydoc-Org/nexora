-- 0095: permissions for the tenant management page (#256 phase 2).
-- admin.view.tenants / admin.edit.tenants, seeded to every access profile that already
-- grants admin.view.organizations -- same rule 0080 used for the clients/processes pages.
-- Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.view.tenants', 'View tenants in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.view.tenants');
GO
INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.edit.tenants', 'Create and edit tenants, their organizations and pages in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.edit.tenants');
GO

-- Schema-adaptive (edited after INT applied it, checksum re-blessed): PROD runs
-- this after 0086 (no Effect column) and 0088 (admin.view.organizations is
-- admin.organizations.view). 0115 then renames the two codes created above.
DECLARE @hasEffect BIT = CASE WHEN COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NULL THEN 0 ELSE 1 END;
DECLARE @sql NVARCHAR(MAX) = N'
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID' + CASE WHEN @hasEffect = 1 THEN N', Effect' ELSE N'' END + N')
SELECT ap.AccessID, np.PermissionID' + CASE WHEN @hasEffect = 1 THEN N', ''A''' ELSE N'' END + N'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code IN (''admin.view.organizations'', ''admin.organizations.view'')
                            ' + CASE WHEN @hasEffect = 1 THEN N'AND ap.Effect = ''A''' ELSE N'' END + N'
CROSS JOIN dbo.Permission np
WHERE np.Code IN (''admin.view.tenants'', ''admin.edit.tenants'')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );';
EXEC sp_executesql @sql;
GO
