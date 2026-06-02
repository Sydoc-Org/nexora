-- 0008_seed_reporting_sql_octopus_permission.sql
-- Adds reporting.sql.target.octopus and grants it to every access profile that
-- already grants admin.view (Effect 'A'), so admins/owner can target the Octopus
-- runtime DB in the live-SQL sandbox out of the box. It is gated independently
-- from reporting.sql.run (Statistics) and remains grantable per-user. Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.sql.target.octopus', 'Reporting: target the Octopus runtime DB in the live-SQL sandbox'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.sql.target.octopus');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.sql.target.octopus'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
