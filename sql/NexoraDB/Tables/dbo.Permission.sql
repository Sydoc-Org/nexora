USE [nexora]
GO
DROP TRIGGER [dbo].[trPermission_GrantEnterpriseAdmin]
GO
DROP TABLE [dbo].[Permission]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Permission](
	[PermissionID] [int] IDENTITY(1,1) NOT NULL,
	[Code] [sysname] NOT NULL,
	[Description] [nvarchar](200) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[PermissionID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
UNIQUE NONCLUSTERED 
(
	[Code] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER OFF
GO

CREATE   TRIGGER [dbo].[trPermission_GrantEnterpriseAdmin]
ON [dbo].[Permission]
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
ALTER TABLE [dbo].[Permission] ENABLE TRIGGER [trPermission_GrantEnterpriseAdmin]
GO
