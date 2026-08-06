USE [nexora]
GO
ALTER TABLE [dbo].[WorkitemFilterViews] DROP CONSTRAINT [FK_WorkitemFilterViews_Users]
GO
ALTER TABLE [dbo].[WorkitemFilterViews] DROP CONSTRAINT [DF_WorkitemFilterViews_CreatedAt]
GO
ALTER TABLE [dbo].[WorkitemFilterViews] DROP CONSTRAINT [DF_WorkitemFilterViews_SortOrder]
GO
DROP TABLE [dbo].[WorkitemFilterViews]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WorkitemFilterViews](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[UserID] [int] NOT NULL,
	[Name] [nvarchar](100) NOT NULL,
	[FilterJSON] [nvarchar](max) NOT NULL,
	[SortOrder] [int] NOT NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[Folder] [nvarchar](100) NULL,
 CONSTRAINT [PK_WorkitemFilterViews] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
 CONSTRAINT [UQ_WorkitemFilterViews_User_Name] UNIQUE NONCLUSTERED 
(
	[UserID] ASC,
	[Name] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[WorkitemFilterViews] ADD  CONSTRAINT [DF_WorkitemFilterViews_SortOrder]  DEFAULT ((0)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[WorkitemFilterViews] ADD  CONSTRAINT [DF_WorkitemFilterViews_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[WorkitemFilterViews]  WITH CHECK ADD  CONSTRAINT [FK_WorkitemFilterViews_Users] FOREIGN KEY([UserID])
REFERENCES [dbo].[Users] ([userID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[WorkitemFilterViews] CHECK CONSTRAINT [FK_WorkitemFilterViews_Users]
GO
