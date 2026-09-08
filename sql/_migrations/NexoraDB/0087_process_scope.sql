-- 0087_process_scope.sql (#238 phase 2)
-- One process.<client>.<name>.view code per (client, process) replaces the
-- three families workitems.filter.process.*, dashboard.filter.process.* and
-- reporting.scope.process.*. Every profile granted the three identically on
-- INT/PROD; the union is taken anyway. User overrides: D wins over A.
DECLARE @old TABLE (PermissionID INT PRIMARY KEY, Pair NVARCHAR(200));
INSERT INTO @old
SELECT PermissionID,
       CASE WHEN Code LIKE 'workitems.filter.process.%' THEN SUBSTRING(Code, LEN('workitems.filter.process.') + 1, 200)
            WHEN Code LIKE 'dashboard.filter.process.%' THEN SUBSTRING(Code, LEN('dashboard.filter.process.') + 1, 200)
            ELSE SUBSTRING(Code, LEN('reporting.scope.process.') + 1, 200) END
FROM dbo.Permission
WHERE Code LIKE 'workitems.filter.process.%' OR Code LIKE 'dashboard.filter.process.%'
   OR Code LIKE 'reporting.scope.process.%';

INSERT INTO dbo.Permission (Code, Description)
SELECT DISTINCT 'process.' + o.Pair + '.view', 'Process ' + o.Pair + ': workitems, dashboard and reports'
FROM @old o
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'process.' + o.Pair + '.view');

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT DISTINCT ap.AccessID, np.PermissionID
FROM dbo.AccessProfilePermission ap
JOIN @old o ON o.PermissionID = ap.PermissionID
JOIN dbo.Permission np ON np.Code = 'process.' + o.Pair + '.view'
WHERE NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x
                  WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID);

INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT uo.UserID, np.PermissionID, MAX(uo.Effect)   -- 'D' > 'A': a deny on any of the three wins
FROM dbo.UserPermissionOverride uo
JOIN @old o ON o.PermissionID = uo.PermissionID
JOIN dbo.Permission np ON np.Code = 'process.' + o.Pair + '.view'
WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride x
                  WHERE x.UserID = uo.UserID AND x.PermissionID = np.PermissionID)
GROUP BY uo.UserID, np.PermissionID;

DELETE FROM dbo.AccessProfilePermission WHERE PermissionID IN (SELECT PermissionID FROM @old);
DELETE FROM dbo.UserPermissionOverride  WHERE PermissionID IN (SELECT PermissionID FROM @old);
DELETE FROM dbo.Permission              WHERE PermissionID IN (SELECT PermissionID FROM @old);
GO
