USE [nexora]
GO
ALTER TABLE [dbo].[AccessProfilePermission] DROP CONSTRAINT [CK_AccessProfilePermission_Effect]
GO
ALTER TABLE [dbo].[AccessProfilePermission] DROP CONSTRAINT [FK_AccessProfilePermission_Permission]
GO
ALTER TABLE [dbo].[AccessProfilePermission] DROP CONSTRAINT [FK_AccessProfilePermission_AccessProfile]
GO
DROP TABLE [dbo].[AccessProfilePermission]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[AccessProfilePermission](
	[AccessID] [int] NOT NULL,
	[PermissionID] [int] NOT NULL,
	[Effect] [char](1) NOT NULL,
 CONSTRAINT [PK_AccessProfilePermission] PRIMARY KEY CLUSTERED 
(
	[AccessID] ASC,
	[PermissionID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[AccessProfilePermission]  WITH CHECK ADD  CONSTRAINT [FK_AccessProfilePermission_AccessProfile] FOREIGN KEY([AccessID])
REFERENCES [dbo].[AccessProfile] ([AccessID])
GO
ALTER TABLE [dbo].[AccessProfilePermission] CHECK CONSTRAINT [FK_AccessProfilePermission_AccessProfile]
GO
ALTER TABLE [dbo].[AccessProfilePermission]  WITH CHECK ADD  CONSTRAINT [FK_AccessProfilePermission_Permission] FOREIGN KEY([PermissionID])
REFERENCES [dbo].[Permission] ([PermissionID])
GO
ALTER TABLE [dbo].[AccessProfilePermission] CHECK CONSTRAINT [FK_AccessProfilePermission_Permission]
GO
ALTER TABLE [dbo].[AccessProfilePermission]  WITH CHECK ADD  CONSTRAINT [CK_AccessProfilePermission_Effect] CHECK  (([Effect]='D' OR [Effect]='A'))
GO
ALTER TABLE [dbo].[AccessProfilePermission] CHECK CONSTRAINT [CK_AccessProfilePermission_Effect]
GO
