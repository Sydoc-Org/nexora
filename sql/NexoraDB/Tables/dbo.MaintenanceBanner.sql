USE [nexora]
GO
ALTER TABLE [dbo].[MaintenanceBanner] DROP CONSTRAINT [DF_MaintenanceBanner_AnnounceMinutesBefore]
GO
ALTER TABLE [dbo].[MaintenanceBanner] DROP CONSTRAINT [DF__Maintenan__Creat__22FF2F51]
GO
ALTER TABLE [dbo].[MaintenanceBanner] DROP CONSTRAINT [DF__Maintenan__Block__220B0B18]
GO
ALTER TABLE [dbo].[MaintenanceBanner] DROP CONSTRAINT [DF__Maintenan__Activ__2116E6DF]
GO
ALTER TABLE [dbo].[MaintenanceBanner] DROP CONSTRAINT [DF__Maintenan__Sever__2022C2A6]
GO
DROP INDEX [IX_MaintenanceBanner_Window] ON [dbo].[MaintenanceBanner]
GO
DROP TABLE [dbo].[MaintenanceBanner]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[MaintenanceBanner](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[Title] [nvarchar](200) NULL,
	[Message] [nvarchar](2000) NOT NULL,
	[StartAt] [datetime2](7) NOT NULL,
	[EndAt] [datetime2](7) NOT NULL,
	[Severity] [varchar](20) NOT NULL,
	[Active] [bit] NOT NULL,
	[BlockAccess] [bit] NOT NULL,
	[CreatedBy] [int] NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[AnnounceMinutesBefore] [int] NULL,
PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_MaintenanceBanner_Window] ON [dbo].[MaintenanceBanner]
(
	[Active] ASC,
	[StartAt] ASC,
	[EndAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ('info') FOR [Severity]
GO
ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ((1)) FOR [Active]
GO
ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ((0)) FOR [BlockAccess]
GO
ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT (getdate()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[MaintenanceBanner] ADD  CONSTRAINT [DF_MaintenanceBanner_AnnounceMinutesBefore]  DEFAULT ((0)) FOR [AnnounceMinutesBefore]
GO
