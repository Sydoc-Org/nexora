USE [nexora]
GO
ALTER TABLE [dbo].[ReportAnnotations] DROP CONSTRAINT [FK_ReportAnnotations_Users]
GO
ALTER TABLE [dbo].[ReportAnnotations] DROP CONSTRAINT [FK_ReportAnnotations_Reports]
GO
ALTER TABLE [dbo].[ReportAnnotations] DROP CONSTRAINT [DF_ReportAnnotations_CreatedAt]
GO
DROP INDEX [IX_ReportAnnotations_Report] ON [dbo].[ReportAnnotations]
GO
DROP TABLE [dbo].[ReportAnnotations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportAnnotations](
	[AnnotationID] [int] IDENTITY(1,1) NOT NULL,
	[ReportID] [int] NOT NULL,
	[BucketKey] [nvarchar](64) NOT NULL,
	[Text] [nvarchar](500) NOT NULL,
	[CreatedBy] [int] NOT NULL,
	[CreatedAt] [datetime2](0) NOT NULL,
 CONSTRAINT [PK_ReportAnnotations] PRIMARY KEY CLUSTERED 
(
	[AnnotationID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_ReportAnnotations_Report] ON [dbo].[ReportAnnotations]
(
	[ReportID] ASC,
	[BucketKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportAnnotations] ADD  CONSTRAINT [DF_ReportAnnotations_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ReportAnnotations]  WITH CHECK ADD  CONSTRAINT [FK_ReportAnnotations_Reports] FOREIGN KEY([ReportID])
REFERENCES [dbo].[Reports] ([ReportID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[ReportAnnotations] CHECK CONSTRAINT [FK_ReportAnnotations_Reports]
GO
ALTER TABLE [dbo].[ReportAnnotations]  WITH CHECK ADD  CONSTRAINT [FK_ReportAnnotations_Users] FOREIGN KEY([CreatedBy])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[ReportAnnotations] CHECK CONSTRAINT [FK_ReportAnnotations_Users]
GO
