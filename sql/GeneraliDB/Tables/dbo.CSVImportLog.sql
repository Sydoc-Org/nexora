USE [Generali]
GO
ALTER TABLE [dbo].[CSVImportLog] DROP CONSTRAINT [DF_CSVImportLog_Status]
GO
ALTER TABLE [dbo].[CSVImportLog] DROP CONSTRAINT [DF_CSVImportLog_RowsUpdated]
GO
ALTER TABLE [dbo].[CSVImportLog] DROP CONSTRAINT [DF_CSVImportLog_RowsInserted]
GO
ALTER TABLE [dbo].[CSVImportLog] DROP CONSTRAINT [DF_CSVImportLog_StartedAt]
GO
DROP INDEX [IX_CSVImportLog_StartedAt] ON [dbo].[CSVImportLog]
GO
DROP TABLE [dbo].[CSVImportLog]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[CSVImportLog](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[FileName] [nvarchar](500) NOT NULL,
	[StartedAt] [datetime] NOT NULL,
	[FinishedAt] [datetime] NULL,
	[CSVRowCount] [int] NULL,
	[RowsInserted] [int] NOT NULL,
	[RowsUpdated] [int] NOT NULL,
	[MinScanDatum] [datetime] NULL,
	[MaxScanDatum] [datetime] NULL,
	[Status] [varchar](20) NOT NULL,
 CONSTRAINT [PK_CSVImportLog] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_CSVImportLog_StartedAt] ON [dbo].[CSVImportLog]
(
	[StartedAt] DESC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[CSVImportLog] ADD  CONSTRAINT [DF_CSVImportLog_StartedAt]  DEFAULT (getdate()) FOR [StartedAt]
GO
ALTER TABLE [dbo].[CSVImportLog] ADD  CONSTRAINT [DF_CSVImportLog_RowsInserted]  DEFAULT ((0)) FOR [RowsInserted]
GO
ALTER TABLE [dbo].[CSVImportLog] ADD  CONSTRAINT [DF_CSVImportLog_RowsUpdated]  DEFAULT ((0)) FOR [RowsUpdated]
GO
ALTER TABLE [dbo].[CSVImportLog] ADD  CONSTRAINT [DF_CSVImportLog_Status]  DEFAULT ('running') FOR [Status]
GO
