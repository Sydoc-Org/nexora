USE [nexora]
GO
ALTER TABLE [dbo].[ReportingSqlAudit] DROP CONSTRAINT [DF_ReportingSqlAudit_CreatedAt]
GO
DROP INDEX [IX_ReportingSqlAudit_User] ON [dbo].[ReportingSqlAudit]
GO
DROP TABLE [dbo].[ReportingSqlAudit]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportingSqlAudit](
	[Id] [int] IDENTITY(1,1) NOT NULL,
	[UserID] [int] NULL,
	[Username] [nvarchar](100) NULL,
	[TargetDB] [nvarchar](50) NOT NULL,
	[SqlText] [nvarchar](max) NOT NULL,
	[RowsReturned] [int] NULL,
	[Status] [nvarchar](16) NOT NULL,
	[DurationMs] [int] NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportingSqlAudit] PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ReportingSqlAudit_User] ON [dbo].[ReportingSqlAudit]
(
	[UserID] ASC,
	[CreatedAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportingSqlAudit] ADD  CONSTRAINT [DF_ReportingSqlAudit_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
