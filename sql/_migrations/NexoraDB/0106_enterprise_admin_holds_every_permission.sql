-- 0106: the Enterprise Admin profile holds every permission, now and later.
-- Owner request 2026-09-07 (#238). Grants every missing code to the profile
-- (renamed from enterpriseAdmin by 0105; both spellings keyed so PROD works
-- whichever order the files land), then a trigger keeps it that way for
-- codes added afterwards -- by migration or via /admin/permissions.
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name IN (N'Enterprise Admin', N'enterpriseAdmin')
  AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x
                  WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID);
GO

CREATE OR ALTER TRIGGER dbo.trPermission_GrantEnterpriseAdmin
ON dbo.Permission
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
    SELECT ap.AccessID, i.PermissionID
    FROM inserted i
    CROSS JOIN dbo.AccessProfile ap
    WHERE ap.Name IN (N'Enterprise Admin', N'enterpriseAdmin')
      AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x
                      WHERE x.AccessID = ap.AccessID AND x.PermissionID = i.PermissionID);
END;
GO
