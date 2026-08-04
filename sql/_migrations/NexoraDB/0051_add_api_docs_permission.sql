-- 0051_add_api_docs_permission.sql
-- New grantable permission for the in-app API documentation page (issue #157):
--   api.docs.view -- see the "API Docs" sidebar entry and the /api-docs page
--     (reference for the external /api/v1/* machine-to-machine API). Meant for
--     internal Sydoc staff and for external API clients' portal accounts.
-- Seeded Effect 'A' to every access profile that already grants admin.view, so
-- admins/owner have it out of the box; grantable per-user beyond that.
-- Idempotent. Mirrors migrations 0018 / 0029 / 0035 / 0044.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'api.docs.view',
       'View the in-app API documentation page (/api-docs)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'api.docs.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'api.docs.view'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
