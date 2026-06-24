-- 0014_seed_reporting_ai_permissions.sql
-- Phase 1 AI assistant permissions:
--   reporting.ai.use  -- ask the assistant
--   reporting.ai.sql  -- receive runnable T-SQL (grant alongside reporting.sql.run)
-- Both seeded to every access profile that already grants admin.view (Effect 'A'),
-- so admins/owner have them out of the box. Grantable per-user. Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.ai.use', 'Reporting: use the AI assistant (NL questions)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.ai.use');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.ai.sql', 'Reporting: receive AI-drafted read-only T-SQL (grant alongside reporting.sql.run)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.ai.sql');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('reporting.ai.use', 'reporting.ai.sql')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
