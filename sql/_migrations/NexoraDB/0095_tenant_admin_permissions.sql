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

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view.organizations' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('admin.view.tenants', 'admin.edit.tenants')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
