USE [nexora]
GO
ALTER TABLE [dbo].[UserPermissionOverride] DROP CONSTRAINT [CK__UserPermi__Effec__367C1819]
GO
ALTER TABLE [dbo].[UserPermissionOverride] DROP CONSTRAINT [FK__UserPermi__UserI__3493CFA7]
GO
ALTER TABLE [dbo].[UserPermissionOverride] DROP CONSTRAINT [FK__UserPermi__Permi__3587F3E0]
GO
DROP TABLE [dbo].[UserPermissionOverride]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[UserPermissionOverride](
	[UserID] [int] NOT NULL,
	[PermissionID] [int] NOT NULL,
	[Effect] [char](1) NOT NULL,
 CONSTRAINT [PK_UserPermissionOverride] PRIMARY KEY CLUSTERED 
(
	[UserID] ASC,
	[PermissionID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[UserPermissionOverride]  WITH CHECK ADD FOREIGN KEY([PermissionID])
REFERENCES [dbo].[Permission] ([PermissionID])
GO
ALTER TABLE [dbo].[UserPermissionOverride]  WITH CHECK ADD FOREIGN KEY([UserID])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[UserPermissionOverride]  WITH CHECK ADD CHECK  (([Effect]='D' OR [Effect]='A'))
GO
