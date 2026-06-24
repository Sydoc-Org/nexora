USE [nexora]
GO
ALTER TABLE [dbo].[ReportingSources] DROP CONSTRAINT [CK_ReportingSources_Kind]
GO
ALTER TABLE [dbo].[ReportingSources] DROP CONSTRAINT [DF_ReportingSources_UpdatedAt]
GO
ALTER TABLE [dbo].[ReportingSources] DROP CONSTRAINT [DF_ReportingSources_CreatedAt]
GO
ALTER TABLE [dbo].[ReportingSources] DROP CONSTRAINT [DF_ReportingSources_SortOrder]
GO
ALTER TABLE [dbo].[ReportingSources] DROP CONSTRAINT [DF_ReportingSources_Enabled]
GO
DROP TABLE [dbo].[ReportingSources]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportingSources](
	[SourceID] [int] IDENTITY(1,1) NOT NULL,
	[Code] [nvarchar](64) NOT NULL,
	[Kind] [nvarchar](16) NOT NULL,
	[Label] [nvarchar](120) NOT NULL,
	[Permission] [nvarchar](128) NOT NULL,
	[Engine] [nvarchar](32) NULL,
	[Target] [nvarchar](32) NULL,
	[Provider] [nvarchar](32) NULL,
	[BaseObject] [nvarchar](256) NULL,
	[ColumnsJSON] [nvarchar](max) NULL,
	[Enabled] [bit] NOT NULL,
	[SortOrder] [int] NOT NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportingSources] PRIMARY KEY CLUSTERED 
(
	[SourceID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
 CONSTRAINT [UQ_ReportingSources_Code] UNIQUE NONCLUSTERED 
(
	[Code] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportingSources] ADD  CONSTRAINT [DF_ReportingSources_Enabled]  DEFAULT ((1)) FOR [Enabled]
GO
ALTER TABLE [dbo].[ReportingSources] ADD  CONSTRAINT [DF_ReportingSources_SortOrder]  DEFAULT ((100)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[ReportingSources] ADD  CONSTRAINT [DF_ReportingSources_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ReportingSources] ADD  CONSTRAINT [DF_ReportingSources_UpdatedAt]  DEFAULT (sysutcdatetime()) FOR [UpdatedAt]
GO
ALTER TABLE [dbo].[ReportingSources]  WITH CHECK ADD  CONSTRAINT [CK_ReportingSources_Kind] CHECK  (([Kind]='sql' OR [Kind]='curated'))
GO
ALTER TABLE [dbo].[ReportingSources] CHECK CONSTRAINT [CK_ReportingSources_Kind]
GO
