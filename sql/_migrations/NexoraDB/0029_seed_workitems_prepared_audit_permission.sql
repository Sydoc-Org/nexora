-- 0029_seed_workitems_prepared_audit_permission.sql
-- New grantable permission for the MS02-only 'prepared documents' Excel import
-- on the workitems list:
--   workitems.import.preparedaudit -- upload a two-column Excel (PID = personal
--     number, Prepared = informational) and display the matched MS02 workitems
--     so their full Octo audit can be reviewed. MS02-only at runtime (the route
--     also gates on engine_ms02_docfields_pg being present); this perm only
--     controls whether the upload control is offered + the route is reachable.
-- Seeded Effect 'A' to every access profile that already grants admin.view, so
-- admins/owner have it out of the box; grantable per-user. Idempotent. Mirrors
-- migration 0018.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.import.preparedaudit',
       'Workitems: import an MS02 prepared-documents Excel (PID/Prepared) and display the matched workitems'' audit'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.import.preparedaudit');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.import.preparedaudit'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
