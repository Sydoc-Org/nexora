-- 0105_profile_names_generali_pdbs_sydoc.sql
-- Profiles get one grammar and the users who sat on the wrong one move:
--   1. "Generali User" (GNRL) holds every Generali portal code, in whichever
--      catalogue shape the DB has (legacy generali.* before #238's 0088,
--      tenant.generali.* after). Generali users on the ISS profiles move there.
--   2. Basel-Stadt is one organization: PDBS. BSPD users move, BSPD goes.
--   3. sydoc staff on customer profiles take the Sydoc profiles; those two
--      profiles gain the PDBS process and the prepared-audit page so nobody
--      loses access by moving.
--   4. Profile names drop camelCase: "<Organization> <Role>". The two assign
--      codes whose slug changes (nexora -> sydoc) follow; every other slug is
--      unchanged because the app strips spaces (nx_lib/security.py).
-- Idempotent; every step keys on both the old and the new profile name.
-- AccessProfilePermission.Effect exists until #238's 0086 drops it, hence the
-- dynamic INSERTs.

-- 1. Generali User ------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM dbo.AccessProfile WHERE Name IN ('GeneraliUser', 'Generali User'))
    INSERT INTO dbo.AccessProfile (Name, Description, OrganizationCode)
    VALUES ('GeneraliUser', 'Generali portal user: every Generali page, every scope', 'GNRL');
GO
DECLARE @g INT = (SELECT AccessID FROM dbo.AccessProfile WHERE Name IN ('GeneraliUser', 'Generali User'));
DECLARE @hasEffect BIT = CASE WHEN COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NULL THEN 0 ELSE 1 END;
DECLARE @sql NVARCHAR(MAX) = N'
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID' + CASE WHEN @hasEffect = 1 THEN N', Effect' ELSE N'' END + N')
SELECT @g, p.PermissionID' + CASE WHEN @hasEffect = 1 THEN N', ''A''' ELSE N'' END + N'
FROM dbo.Permission p
WHERE (p.Code LIKE ''generali.%''
       OR (p.Code LIKE ''tenant.generali.%'' AND p.Code NOT IN (''tenant.generali.view'', ''tenant.generali.edit'')))
  AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x WHERE x.AccessID = @g AND x.PermissionID = p.PermissionID);';
EXEC sp_executesql @sql, N'@g INT', @g = @g;

-- INT oddity: the profile also held the MS02 tenant codes.
DELETE ap
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission p ON p.PermissionID = ap.PermissionID
WHERE ap.AccessID = @g AND p.Code LIKE 'tenant.ms02.%';

-- Generali users seated on the ISS profiles.
UPDATE dbo.Users SET accessid = @g
WHERE organizationCode = 'GNRL'
  AND accessid IN (SELECT AccessID FROM dbo.AccessProfile
                   WHERE Name IN ('issUser', 'issSupervisor', 'ISS User', 'ISS Supervisor'));
GO

-- 2. One Basel-Stadt organization: PDBS -----------------------------------------
UPDATE dbo.Users          SET organizationCode = 'PDBS' WHERE organizationCode = 'BSPD';
UPDATE dbo.AccessProfile  SET OrganizationCode = 'PDBS' WHERE OrganizationCode = 'BSPD';
UPDATE dbo.ProcessSources SET OrganizationCode = 'PDBS' WHERE OrganizationCode = 'BSPD';
DELETE FROM dbo.Organizations WHERE organizationcode = 'BSPD';
GO

-- 3. sydoc staff take the Sydoc profiles ----------------------------------------
DECLARE @su INT = (SELECT AccessID FROM dbo.AccessProfile WHERE Name IN ('nexoraUser', 'Sydoc User'));
DECLARE @ss INT = (SELECT AccessID FROM dbo.AccessProfile WHERE Name IN ('nexoraSupervisor', 'Sydoc Supervisor'));
UPDATE u SET accessid = CASE WHEN a.Name LIKE '%Supervisor' THEN @ss ELSE @su END
FROM dbo.Users u
JOIN dbo.AccessProfile a ON a.AccessID = u.accessid
WHERE u.organizationCode = 'SYDC'
  AND a.Name NOT IN ('enterpriseAdmin', 'Enterprise Admin', 'globalAdmin', 'Global Admin',
                     'nexoraUser', 'Sydoc User', 'nexoraSupervisor', 'Sydoc Supervisor');

-- Staff see every customer's processes; the Sydoc profiles lacked PDBS and prepared-audit.
DECLARE @hasEffect BIT = CASE WHEN COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NULL THEN 0 ELSE 1 END;
DECLARE @sql NVARCHAR(MAX) = N'
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID' + CASE WHEN @hasEffect = 1 THEN N', Effect' ELSE N'' END + N')
SELECT a.AccessID, p.PermissionID' + CASE WHEN @hasEffect = 1 THEN N', ''A''' ELSE N'' END + N'
FROM dbo.AccessProfile a
CROSS JOIN dbo.Permission p
WHERE a.AccessID IN (@su, @ss)
  AND p.Code IN (''dashboard.filter.process.sydoc.05_PDBS'', ''workitems.filter.process.sydoc.05_PDBS'',
                 ''reporting.scope.process.sydoc.05_PDBS'', ''process.sydoc.05_PDBS.view'',
                 ''workitems.import.preparedaudit'', ''workitems.prepared.view'')
  AND NOT EXISTS (SELECT 1 FROM dbo.AccessProfilePermission x WHERE x.AccessID = a.AccessID AND x.PermissionID = p.PermissionID);';
EXEC sp_executesql @sql, N'@su INT, @ss INT', @su = @su, @ss = @ss;
GO

-- 4. Names: "<Organization> <Role>" ---------------------------------------------
UPDATE dbo.AccessProfile SET Name = CASE Name
    WHEN 'enterpriseAdmin'     THEN 'Enterprise Admin'
    WHEN 'globalAdmin'         THEN 'Global Admin'
    WHEN 'nexoraSupervisor'    THEN 'Sydoc Supervisor'
    WHEN 'nexoraUser'          THEN 'Sydoc User'
    WHEN 'issSupervisor'       THEN 'ISS Supervisor'
    WHEN 'issUser'             THEN 'ISS User'
    WHEN 'pdbsUser'            THEN 'PDBS User'
    WHEN 'priveraUser'         THEN 'Privera User'
    WHEN 'compassUser'         THEN 'Compass User'
    WHEN 'elektromaterialUser' THEN 'ElektroMaterial User'
    WHEN 'GeneraliUser'        THEN 'Generali User'
    ELSE Name END
WHERE Name IN ('enterpriseAdmin', 'globalAdmin', 'nexoraSupervisor', 'nexoraUser', 'issSupervisor', 'issUser',
               'pdbsUser', 'priveraUser', 'compassUser', 'elektromaterialUser', 'GeneraliUser');

-- The assign codes are slugs of the name; only the renamed root changes.
-- (Both rows are already gone on a DB past #238's 0086; these then touch nothing.)
UPDATE dbo.Permission SET Code = 'admin.assign.user.accessprofile.sydocuser'
WHERE Code = 'admin.assign.user.accessprofile.nexorauser';
UPDATE dbo.Permission SET Code = 'admin.assign.user.accessprofile.sydocsupervisor'
WHERE Code = 'admin.assign.user.accessprofile.nexorasupervisor';
GO
