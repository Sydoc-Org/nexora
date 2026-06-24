-- 0007_seed_reporting_sql_permission.sql
-- Adds reporting.sql.run and grants it to every access profile that already
-- grants admin.view (Effect 'A'), so admins/owner have the live-SQL capability
-- out of the box. It remains grantable per-user. Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.sql.run', 'Reporting: run live read-only SQL (sandboxed)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.sql.run');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.sql.run'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
