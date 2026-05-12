USE [nexora]
GO
ALTER TABLE [dbo].[Notifications] DROP CONSTRAINT [FK_Notifications_Users]
GO
ALTER TABLE [dbo].[Notifications] DROP CONSTRAINT [DF__Notificat__Times__3F115E1A]
GO
ALTER TABLE [dbo].[Notifications] DROP CONSTRAINT [DF__Notificat__IsRea__48CFD27E]
GO
DROP TABLE [dbo].[Notifications]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Notifications](
	[NotificationID] [int] IDENTITY(3000,1) NOT NULL,
	[UserID] [int] NOT NULL,
	[Message] [nvarchar](512) NOT NULL,
	[Link] [nvarchar](255) NULL,
	[Icon] [nvarchar](50) NULL,
	[IsRead] [bit] NOT NULL,
	[Timestamp] [datetime2](7) NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[NotificationID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Notifications] ADD  DEFAULT ((0)) FOR [IsRead]
GO
ALTER TABLE [dbo].[Notifications] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO
ALTER TABLE [dbo].[Notifications]  WITH CHECK ADD  CONSTRAINT [FK_Notifications_Users] FOREIGN KEY([UserID])
REFERENCES [dbo].[Users] ([userID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[Notifications] CHECK CONSTRAINT [FK_Notifications_Users]
GO
