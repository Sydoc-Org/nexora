-- 0086_permission_cleanup_and_rank.sql  (#238 phase 1)
-- Profile grants become allow-only: a profile-level DENY was identical to "no
-- row" (one profile per user, default deny). Adds AccessProfile.Rank, which
-- replaces the ten admin.assign.user.accessprofile.* codes (rule: an actor may
-- assign a profile whose Rank <= their own). Deletes orphan codes. Rewrites
-- the resolver function and the set-based permission proc.

DELETE FROM dbo.AccessProfilePermission WHERE Effect = 'D';
GO
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_AccessProfilePermission_Effect')
    ALTER TABLE dbo.AccessProfilePermission DROP CONSTRAINT CK_AccessProfilePermission_Effect;
GO
IF COL_LENGTH('dbo.AccessProfilePermission', 'Effect') IS NOT NULL
    ALTER TABLE dbo.AccessProfilePermission DROP COLUMN Effect;
GO
IF COL_LENGTH('dbo.AccessProfile', 'Rank') IS NULL
    ALTER TABLE dbo.AccessProfile ADD Rank INT NOT NULL CONSTRAINT DF_AccessProfile_Rank DEFAULT 0;
GO
UPDATE dbo.AccessProfile SET Rank = CASE
    WHEN Name = 'enterpriseAdmin' THEN 100
    WHEN Name = 'globalAdmin' THEN 90
    WHEN Name LIKE '%Supervisor' THEN 50
    ELSE 10 END
WHERE Rank = 0;
GO
-- Orphans (retired invoices page #177, Kundenmagazin, two dead admin codes)
-- and the ten assign meta-codes. Grant rows first (FKs), then the codes.
DECLARE @dead TABLE (PermissionID INT PRIMARY KEY);
INSERT INTO @dead SELECT PermissionID FROM dbo.Permission
WHERE Code LIKE 'invoices.%' OR Code LIKE 'kundenmagazin.%'
   OR Code IN ('admin.interact.users.all', 'admin.view.mobscn.processmanagement')
   OR Code LIKE 'admin.assign.user.accessprofile.%';
DELETE FROM dbo.AccessProfilePermission WHERE PermissionID IN (SELECT PermissionID FROM @dead);
DELETE FROM dbo.UserPermissionOverride  WHERE PermissionID IN (SELECT PermissionID FROM @dead);
DELETE FROM dbo.Permission              WHERE PermissionID IN (SELECT PermissionID FROM @dead);
GO
CREATE OR ALTER FUNCTION dbo.fnUserHasPermission (@UserID INT, @PermCode SYSNAME)
RETURNS BIT AS
BEGIN
    DECLARE @PermID INT = (SELECT PermissionID FROM dbo.Permission WHERE Code = @PermCode);
    IF @PermID IS NULL RETURN 0;
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'D') RETURN 0;
    IF EXISTS (SELECT 1 FROM dbo.UserPermissionOverride
               WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'A') RETURN 1;
    IF EXISTS (SELECT 1 FROM dbo.Users u
               JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
               WHERE u.userID = @UserID AND ap.PermissionID = @PermID) RETURN 1;
    RETURN 0;
END;
GO
CREATE OR ALTER PROCEDURE dbo.spGetUserPermissions @UserID INT AS
BEGIN
    SET NOCOUNT ON;
    SELECT p.Code
    FROM dbo.Permission p
    WHERE NOT EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                      WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'D')
      AND ( EXISTS (SELECT 1 FROM dbo.UserPermissionOverride o
                    WHERE o.UserID = @UserID AND o.PermissionID = p.PermissionID AND o.Effect = 'A')
         OR EXISTS (SELECT 1 FROM dbo.Users u
                    JOIN dbo.AccessProfilePermission ap ON ap.AccessID = u.accessid
                    WHERE u.userID = @UserID AND ap.PermissionID = p.PermissionID) );
END;
GO
