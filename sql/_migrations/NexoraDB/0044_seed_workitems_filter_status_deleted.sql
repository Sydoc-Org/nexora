-- 0044_seed_workitems_filter_status_deleted.sql
-- New grantable permission for the workitems list (issue #125):
--   workitems.filter.status.deleted -- offer "Deleted" in the status filter and
--     let the query return soft-deleted workitems (Octo/MS02 Status = 2, which
--     every other view hard-excludes). Internal-only: meant for Sydoc staff
--     diagnosing what happened to a workitem, not for customer accounts.
--     Only meaningful together with workitems.filter.status (the dropdown is
--     disabled without it), which the backend enforces -- the "Deleted" value is
--     only mapped to a status code when BOTH perms are held; otherwise it falls
--     through to the default query, which still carries `Status <> 2`.
-- Seeded Effect 'A' to every access profile that already grants admin.view, so
-- admins/owner have it out of the box; grantable per-user. Idempotent. Mirrors
-- migrations 0018 / 0029 / 0035.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.filter.status.deleted',
       'Workitems: filter for and view deleted workitems (internal only; needs workitems.filter.status)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.filter.status.deleted');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.filter.status.deleted'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
