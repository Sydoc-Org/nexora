-- 0015_seed_reporting_ai_explain_data.sql
-- Phase 3e AI assistant permission:
--   reporting.ai.explain_data  -- let the agentic loop run read-only SELECTs and
--     compute deterministic stats whose RESULTS flow back to the model so it can
--     narrate actual numbers. This is a data-egress grant (result rows reach the
--     LLM), so it is deliberately separate from reporting.ai.use / reporting.ai.sql
--     and is only effective together with reporting.sql.run (the live-SQL gate).
-- Seeded to every access profile that already grants admin.view (Effect 'A'), so
-- admins/owner have it out of the box; grantable per-user. Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.ai.explain_data',
       'Reporting: let the AI assistant run read-only queries and explain the actual result numbers (data egress to the model; needs reporting.sql.run)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.ai.explain_data');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.ai.explain_data'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
