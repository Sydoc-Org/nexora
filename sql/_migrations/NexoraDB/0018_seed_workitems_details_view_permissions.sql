-- 0018_seed_workitems_details_view_permissions.sql
-- Two new sub-permissions for the workitems document viewer / source highlighting:
--   workitems.details.view.confidence       -- see the extraction confidence %
--     (the per-field/cell confidence chips + the confidence colour on the boxes).
--   workitems.details.view.source_location  -- see WHERE each extracted value was
--     found on the page (the highlight boxes + click-to-locate). Only meaningful
--     together with workitems.details.view.images (boxes are drawn over the page
--     image), which the backend enforces.
-- Both seeded to every access profile that already grants admin.view (Effect 'A'),
-- so admins/owner have them out of the box; grantable per-user. Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.details.view.confidence',
       'Workitems: view extraction confidence scores in the document viewer'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.details.view.confidence');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'workitems.details.view.source_location',
       'Workitems: view where extracted values were found on the page (source-highlight boxes; needs workitems.details.view.images)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'workitems.details.view.source_location');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.details.view.confidence'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'workitems.details.view.source_location'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
