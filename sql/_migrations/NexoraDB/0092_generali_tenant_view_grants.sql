-- 0092: grant tenant.generali.view to whoever already reaches a Generali page (#257).
--
-- 0091's grant step matched nothing: AccessProfilePermission.Effect is 'A'/'D' (not
-- 'ALLOW'), and the only personal Generali overrides on INT are .add/.edit codes, not
-- .view. Migrations are immutable once applied, so the corrected grant lives here.
--
-- Profiles that grant any generali.* permission get tenant.generali.view as a profile
-- permission (globalAdmin today); users holding any personal generali.* allow get it
-- as a personal override. Nobody gets tenant.generali.edit.

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT DISTINCT app.AccessID, tv.PermissionID, 'A'
  FROM dbo.AccessProfilePermission app
  JOIN dbo.Permission p  ON p.PermissionID = app.PermissionID
  JOIN dbo.Permission tv ON tv.Code = 'tenant.generali.view'
 WHERE app.Effect = 'A' AND p.Code LIKE 'generali.%'
   AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = app.AccessID AND x.PermissionID = tv.PermissionID
       );
GO

INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT DISTINCT o.UserID, tv.PermissionID, 'A'
  FROM dbo.UserPermissionOverride o
  JOIN dbo.Permission p  ON p.PermissionID = o.PermissionID
  JOIN dbo.Permission tv ON tv.Code = 'tenant.generali.view'
 WHERE o.Effect = 'A' AND p.Code LIKE 'generali.%'
   AND NOT EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride x
        WHERE x.UserID = o.UserID AND x.PermissionID = tv.PermissionID
       );
GO
