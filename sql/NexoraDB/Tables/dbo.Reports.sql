USE [nexora]
GO
ALTER TABLE [dbo].[Reports] DROP CONSTRAINT [FK_Reports_Users]
GO
ALTER TABLE [dbo].[Reports] DROP CONSTRAINT [DF_Reports_UpdatedAt]
GO
ALTER TABLE [dbo].[Reports] DROP CONSTRAINT [DF_Reports_CreatedAt]
GO
DROP INDEX [IX_Reports_Owner] ON [dbo].[Reports]
GO
DROP TABLE [dbo].[Reports]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Reports](
	[ReportID] [int] IDENTITY(1,1) NOT NULL,
	[OwnerUserID] [int] NOT NULL,
	[Name] [nvarchar](200) NOT NULL,
	[DefinitionJSON] [nvarchar](max) NOT NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_Reports] PRIMARY KEY CLUSTERED 
(
	[ReportID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Reports_Owner] ON [dbo].[Reports]
(
	[OwnerUserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Reports] ADD  CONSTRAINT [DF_Reports_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[Reports] ADD  CONSTRAINT [DF_Reports_UpdatedAt]  DEFAULT (sysutcdatetime()) FOR [UpdatedAt]
GO
ALTER TABLE [dbo].[Reports]  WITH CHECK ADD  CONSTRAINT [FK_Reports_Users] FOREIGN KEY([OwnerUserID])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[Reports] CHECK CONSTRAINT [FK_Reports_Users]
GO
