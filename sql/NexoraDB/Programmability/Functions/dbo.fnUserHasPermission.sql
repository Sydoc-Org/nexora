USE [nexora]
GO
DROP FUNCTION [dbo].[fnUserHasPermission]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER OFF
GO
CREATE   FUNCTION [dbo].[fnUserHasPermission] (@UserID INT, @PermCode SYSNAME)
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
