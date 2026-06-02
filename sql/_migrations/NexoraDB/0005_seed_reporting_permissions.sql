-- 0005_seed_reporting_permissions.sql
-- Adds reporting.* permission codes and grants them to whichever access profiles
-- already grant admin.view (Effect 'A'). Also mirrors each existing
-- dashboard.filter.process.<client>.<process> grant into a separate
-- reporting.scope.process.<client>.<process> permission, so users who can see a
-- process on the dashboard can include it in reports. Idempotent throughout.

-- 1) base reporting permission codes
INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    ('reporting.view',                  'Access the Reporting page'),
    ('reporting.source.docprocessing',  'Reporting: use the Document Processing source'),
    ('reporting.export',                'Reporting: export reports to Excel')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

-- 2) scope perms mirrored from dashboard.filter.process.*
INSERT INTO dbo.Permission (Code, Description)
SELECT REPLACE(p.Code, 'dashboard.filter.process.', 'reporting.scope.process.'),
       CONCAT('Reporting scope: ', REPLACE(p.Code, 'dashboard.filter.process.', ''))
FROM dbo.Permission p
WHERE p.Code LIKE 'dashboard.filter.process.%'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.Permission p2
        WHERE p2.Code = REPLACE(p.Code, 'dashboard.filter.process.', 'reporting.scope.process.')
  );
GO

-- 3) grant base reporting perms to every profile that grants admin.view ('A')
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code IN ('reporting.view', 'reporting.source.docprocessing', 'reporting.export')
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- 4) grant each reporting.scope.process.* to the same profiles that grant the
--    matching dashboard.filter.process.* ('A')
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, rp.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission dp ON dp.PermissionID = ap.PermissionID
                       AND dp.Code LIKE 'dashboard.filter.process.%' AND ap.Effect = 'A'
JOIN dbo.Permission rp ON rp.Code = REPLACE(dp.Code, 'dashboard.filter.process.', 'reporting.scope.process.')
WHERE NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = rp.PermissionID
);
GO
