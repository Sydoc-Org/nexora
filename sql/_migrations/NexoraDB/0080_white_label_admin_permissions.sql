-- 0080_white_label_admin_permissions.sql
-- New grantable permissions for the white-label admin UI (issue #98 phase 4):
-- admin.view.clients / admin.edit.clients (client registry pages),
-- admin.view.processes / admin.edit.processes (process source mapping pages),
-- admin.edit.organization.branding (tenant branding editor).
-- Seeded to every access profile that already grants admin.view.organizations.
-- Idempotent. Mirrors migration 0059.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.view.clients',
       'View the client registry in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.view.clients');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.edit.clients',
       'Edit the client registry in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.edit.clients');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.view.processes',
       'View process source mappings in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.view.processes');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.edit.processes',
       'Edit process source mappings in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.edit.processes');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.edit.organization.branding',
       'Edit tenant branding in the admin UI'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.edit.organization.branding');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view.organizations' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('admin.view.clients', 'admin.edit.clients',
                   'admin.view.processes', 'admin.edit.processes',
                   'admin.edit.organization.branding')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
