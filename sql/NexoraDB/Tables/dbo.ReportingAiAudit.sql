USE [nexora]
GO
ALTER TABLE [dbo].[ReportingAiAudit] DROP CONSTRAINT [DF_ReportingAiAudit_CreatedAt]
GO
DROP INDEX [IX_ReportingAiAudit_User] ON [dbo].[ReportingAiAudit]
GO
DROP TABLE [dbo].[ReportingAiAudit]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportingAiAudit](
	[Id] [int] IDENTITY(1,1) NOT NULL,
	[UserID] [int] NULL,
	[Username] [nvarchar](100) NULL,
	[Prompt] [nvarchar](max) NOT NULL,
	[Surface] [nvarchar](16) NOT NULL,
	[GeneratedSql] [nvarchar](max) NULL,
	[Model] [nvarchar](100) NULL,
	[Provider] [nvarchar](32) NULL,
	[TokensIn] [int] NULL,
	[TokensOut] [int] NULL,
	[GateVerdict] [nvarchar](16) NULL,
	[Status] [nvarchar](16) NOT NULL,
	[DurationMs] [int] NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportingAiAudit] PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ReportingAiAudit_User] ON [dbo].[ReportingAiAudit]
(
	[UserID] ASC,
	[CreatedAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportingAiAudit] ADD  CONSTRAINT [DF_ReportingAiAudit_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
