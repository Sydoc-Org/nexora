USE [nexora]
GO
DROP PROCEDURE [dbo].[spGetUserPermissions]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER OFF
GO
CREATE   PROCEDURE [dbo].[spGetUserPermissions] @UserID INT AS
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
