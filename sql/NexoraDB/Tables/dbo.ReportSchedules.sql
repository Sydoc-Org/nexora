USE [nexora]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [CK_ReportSchedules_Frequency]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [CK_ReportSchedules_Format]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [FK_ReportSchedules_Users]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [FK_ReportSchedules_Reports]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_UpdatedAt]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_CreatedAt]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_Enabled]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_Minute]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_Hour]
GO
ALTER TABLE [dbo].[ReportSchedules] DROP CONSTRAINT [DF_ReportSchedules_Format]
GO
DROP INDEX [IX_ReportSchedules_Due] ON [dbo].[ReportSchedules]
GO
DROP TABLE [dbo].[ReportSchedules]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportSchedules](
	[ScheduleID] [int] IDENTITY(1,1) NOT NULL,
	[ReportID] [int] NOT NULL,
	[OwnerUserID] [int] NOT NULL,
	[Recipients] [nvarchar](1000) NOT NULL,
	[Format] [nvarchar](8) NOT NULL,
	[Frequency] [nvarchar](10) NOT NULL,
	[Hour] [tinyint] NOT NULL,
	[Minute] [tinyint] NOT NULL,
	[Weekday] [tinyint] NULL,
	[DayOfMonth] [tinyint] NULL,
	[Enabled] [bit] NOT NULL,
	[LastRunAt] [datetime2](7) NULL,
	[NextRunAt] [datetime2](7) NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportSchedules] PRIMARY KEY CLUSTERED 
(
	[ScheduleID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ReportSchedules_Due] ON [dbo].[ReportSchedules]
(
	[Enabled] ASC,
	[NextRunAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_Format]  DEFAULT ('xlsx') FOR [Format]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_Hour]  DEFAULT ((6)) FOR [Hour]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_Minute]  DEFAULT ((0)) FOR [Minute]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_Enabled]  DEFAULT ((1)) FOR [Enabled]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ReportSchedules] ADD  CONSTRAINT [DF_ReportSchedules_UpdatedAt]  DEFAULT (sysutcdatetime()) FOR [UpdatedAt]
GO
ALTER TABLE [dbo].[ReportSchedules]  WITH CHECK ADD  CONSTRAINT [FK_ReportSchedules_Reports] FOREIGN KEY([ReportID])
REFERENCES [dbo].[Reports] ([ReportID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[ReportSchedules] CHECK CONSTRAINT [FK_ReportSchedules_Reports]
GO
ALTER TABLE [dbo].[ReportSchedules]  WITH CHECK ADD  CONSTRAINT [FK_ReportSchedules_Users] FOREIGN KEY([OwnerUserID])
REFERENCES [dbo].[Users] ([userID])
GO
ALTER TABLE [dbo].[ReportSchedules] CHECK CONSTRAINT [FK_ReportSchedules_Users]
GO
ALTER TABLE [dbo].[ReportSchedules]  WITH CHECK ADD  CONSTRAINT [CK_ReportSchedules_Format] CHECK  (([Format]='csv' OR [Format]='xlsx'))
GO
ALTER TABLE [dbo].[ReportSchedules] CHECK CONSTRAINT [CK_ReportSchedules_Format]
GO
ALTER TABLE [dbo].[ReportSchedules]  WITH CHECK ADD  CONSTRAINT [CK_ReportSchedules_Frequency] CHECK  (([Frequency]='monthly' OR [Frequency]='weekly' OR [Frequency]='daily'))
GO
ALTER TABLE [dbo].[ReportSchedules] CHECK CONSTRAINT [CK_ReportSchedules_Frequency]
GO
