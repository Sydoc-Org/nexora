-- 0059_add_admin_restart_permission.sql
-- New grantable permission for the dev-only "Restart nexora" button on the
-- admin overview page (issue #184): admin.restart -- POST /api/admin/restart,
-- which kills and respawns the local dev server so template/code changes show
-- up without a manual `nx -r`. Route 404s on PROD regardless of this grant.
-- Seeded Effect 'A' to every access profile that already grants admin.view.
-- Idempotent. Mirrors migration 0051.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.restart',
       'Restart the local dev server from the admin overview page (dev-only)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.restart');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'admin.restart'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
