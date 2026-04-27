USE [nexora]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE PROCEDURE [dbo].[spGetUserPermissions]
    @UserID INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT DISTINCT p.Code
    FROM dbo.Permission p
    WHERE dbo.fnUserHasPermission(@UserID, p.Code) = 1;
END;
GO


