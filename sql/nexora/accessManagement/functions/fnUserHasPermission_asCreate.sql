USE [nexora]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE FUNCTION [dbo].[fnUserHasPermission]
(
    @UserID     INT,
    @PermCode   SYSNAME
)
RETURNS BIT
AS
BEGIN
    DECLARE @PermID INT;
    SELECT @PermID = PermissionID
    FROM dbo.Permission
    WHERE Code = @PermCode;

    IF @PermID IS NULL
        RETURN 0;

    --User-level DENY
    IF EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride
        WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'D'
    )
        RETURN 0;

    --User-level ALLOW
    IF EXISTS (
        SELECT 1 FROM dbo.UserPermissionOverride
        WHERE UserID = @UserID AND PermissionID = @PermID AND Effect = 'A'
    )
        RETURN 1;

    --Access profile DENY
    IF EXISTS (
        SELECT 1
        FROM dbo.Users u
        JOIN dbo.AccessProfilePermission ap
          ON ap.AccessID = u.accessID
        WHERE u.userID = @UserID
          AND ap.PermissionID = @PermID
          AND ap.Effect = 'D'
    )
        RETURN 0;

    --Access profile ALLOW
    IF EXISTS (
        SELECT 1
        FROM dbo.Users u
        JOIN dbo.AccessProfilePermission ap
          ON ap.AccessID = u.accessID
        WHERE u.userID = @UserID
          AND ap.PermissionID = @PermID
          AND ap.Effect = 'A'
    )
        RETURN 1;

    RETURN 0;  -- default deny
END;
GO


