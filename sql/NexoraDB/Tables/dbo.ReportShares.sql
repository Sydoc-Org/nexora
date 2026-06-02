USE [nexora]
GO
ALTER TABLE [dbo].[ReportShares] DROP CONSTRAINT [FK_ReportShares_Users]
GO
ALTER TABLE [dbo].[ReportShares] DROP CONSTRAINT [FK_ReportShares_Reports]
GO
ALTER TABLE [dbo].[ReportShares] DROP CONSTRAINT [DF_ReportShares_CreatedAt]
GO
ALTER TABLE [dbo].[ReportShares] DROP CONSTRAINT [DF_ReportShares_CanEdit]
GO
DROP INDEX [IX_ReportShares_User] ON [dbo].[ReportShares]
GO
DROP TABLE [dbo].[ReportShares]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportShares](
	[ReportID] [int] NOT NULL,
	[SharedWithUserID] [int] NOT NULL,
	[CanEdit] [bit] NOT NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportShares] PRIMARY KEY CLUSTERED 
(
	[ReportID] ASC,
	[SharedWithUserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ReportShares_User] ON [dbo].[ReportShares]
(
	[SharedWithUserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportShares] ADD  CONSTRAINT [DF_ReportShares_CanEdit]  DEFAULT ((0)) FOR [CanEdit]
GO
ALTER TABLE [dbo].[ReportShares] ADD  CONSTRAINT [DF_ReportShares_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ReportShares]  WITH CHECK ADD  CONSTRAINT [FK_ReportShares_Reports] FOREIGN KEY([ReportID])
REFERENCES [dbo].[Reports] ([ReportID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[ReportShares] CHECK CONSTRAINT [FK_ReportShares_Reports]
GO
ALTER TABLE [dbo].[ReportShares]  WITH CHECK ADD  CONSTRAINT [FK_ReportShares_Users] FOREIGN KEY([SharedWithUserID])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[ReportShares] CHECK CONSTRAINT [FK_ReportShares_Users]
GO
