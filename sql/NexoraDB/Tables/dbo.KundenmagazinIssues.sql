USE [nexora]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] DROP CONSTRAINT [DF_KundenmagazinIssues_VisibleToAll]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] DROP CONSTRAINT [DF__Kundenmag__Uploa__38B96646]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] DROP CONSTRAINT [DF__Kundenmag__IsPub__37C5420D]
GO
DROP INDEX [IX_KundenmagazinIssues_PublishedOn] ON [dbo].[KundenmagazinIssues]
GO
DROP TABLE [dbo].[KundenmagazinIssues]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[KundenmagazinIssues](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[Title] [nvarchar](200) NOT NULL,
	[IssueLabel] [nvarchar](50) NULL,
	[Summary] [nvarchar](1000) NULL,
	[PublishedOn] [date] NULL,
	[StoredFileName] [nvarchar](260) NOT NULL,
	[OriginalFileName] [nvarchar](260) NULL,
	[FileSizeBytes] [bigint] NULL,
	[PageCount] [int] NULL,
	[IsPublished] [bit] NOT NULL,
	[UploadedBy] [int] NULL,
	[UploadedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NULL,
	[VisibleToAll] [bit] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_KundenmagazinIssues_PublishedOn] ON [dbo].[KundenmagazinIssues]
(
	[IsPublished] ASC,
	[PublishedOn] DESC,
	[ID] DESC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] ADD  DEFAULT ((1)) FOR [IsPublished]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] ADD  DEFAULT (sysutcdatetime()) FOR [UploadedAt]
GO
ALTER TABLE [dbo].[KundenmagazinIssues] ADD  CONSTRAINT [DF_KundenmagazinIssues_VisibleToAll]  DEFAULT ((1)) FOR [VisibleToAll]
GO
