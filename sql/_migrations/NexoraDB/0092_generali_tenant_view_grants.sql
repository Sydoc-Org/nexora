-- 0092: grant tenant.generali.view to whoever already reaches a Generali page (#257).
--
-- 0091's grant step matched nothing: AccessProfilePermission.Effect is 'A'/'D' (not
-- 'ALLOW'), and the only personal Generali overrides on INT are .add/.edit codes, not
-- .view. Migrations are immutable once applied, so the corrected grant lives here.
--
-- Profiles that grant any generali.* permission get tenant.generali.view as a profile
-- permission (globalAdmin today); users holding any personal generali.* allow get it
-- as a personal override. Nobody gets tenant.generali.edit.

-- Schema-adaptive (edited after INT applied it, checksum re-blessed): on PROD
-- this runs after 0086 (no AccessProfilePermission.Effect; every row is a grant)
-- and after 0088 (generali.* became tenant.generali.*), so both column shapes
-- and both code shapes are handled. Batch-level binding is why the Effect
-- variant sits in sp_executesql -- see docs/howto/db-migrations.md.
DECLARE @hasEffect BIT = CASE WHEN COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NULL THEN 0 ELSE 1 END;
DECLARE @sql NVARCHAR(MAX) = N'
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID' + CASE WHEN @hasEffect = 1 THEN N', Effect' ELSE N'' END + N')
SELECT DISTINCT app.AccessID, tv.PermissionID' + CASE WHEN @hasEffect = 1 THEN N', ''A''' ELSE N'' END + N'
  FROM dbo.AccessProfilePermission app
  JOIN dbo.Permission p  ON p.PermissionID = app.PermissionID
  JOIN dbo.Permission tv ON tv.Code = ''tenant.generali.view''
 WHERE ' + CASE WHEN @hasEffect = 1 THEN N'app.Effect = ''A'' AND ' ELSE N'' END + N'
       (p.Code LIKE ''generali.%'' OR (p.Code LIKE ''tenant.generali.%''
                                      AND p.Code NOT IN (''tenant.generali.view'', ''tenant.generali.edit'')))
   AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = app.AccessID AND x.PermissionID = tv.PermissionID
       );';
EXEC sp_executesql @sql;
GO

INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT DISTINCT o.UserID, tv.PermissionID, 'A'
  FROM dbo.UserPermissionOverride o
  JOIN dbo.Permission p  ON p.PermissionID = o.PermissionID
  JOIN dbo.Permission tv ON tv.Code = 'tenant.generali.view'
 WHERE o.Effect = 'A'
   AND (p.Code LIKE 'generali.%' OR (p.Code LIKE 'tenant.generali.%'
                                     AND p.Code NOT IN ('tenant.generali.view', 'tenant.generali.edit')))
   AND NOT EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride x
        WHERE x.UserID = o.UserID AND x.PermissionID = tv.PermissionID
       );
GO
