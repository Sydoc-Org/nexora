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
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
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
