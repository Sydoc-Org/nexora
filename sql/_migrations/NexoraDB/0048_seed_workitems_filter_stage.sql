-- 0048_seed_workitems_filter_stage.sql
-- New grantable permission for the workitems list (issue #147):
--   workitems.filter.stage -- offer the "Stage" dropdown (Import / Extraction /
--     Validation / Delivery) in the top filter row and let the query constrain
--     on a workitem's latest derived stage.
-- Seeded Effect 'A' to every access profile that already grants
-- workitems.filter.status='A' -- the stage filter sits next to status in the
-- UI, so anyone who can already filter by status gets stage for free; still
-- grantable independently per-user. Idempotent. Mirrors migration 0044.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.filter.stage',
       'Workitems: filter by process stage (Import/Extraction/Validation/Delivery)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.filter.stage');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission status_p ON status_p.PermissionID = ap.PermissionID
                             AND status_p.Code = 'workitems.filter.status' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.filter.stage'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
