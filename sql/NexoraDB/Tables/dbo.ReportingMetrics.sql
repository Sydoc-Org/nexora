USE [nexora]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [CK_ReportingMetrics_TotalMode]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [CK_ReportingMetrics_Aggregation]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [DF_ReportingMetrics_TotalMode]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [DF_ReportingMetrics_UpdatedAt]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [DF_ReportingMetrics_CreatedAt]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [DF_ReportingMetrics_SortOrder]
GO
ALTER TABLE [dbo].[ReportingMetrics] DROP CONSTRAINT [DF_ReportingMetrics_Enabled]
GO
DROP TABLE [dbo].[ReportingMetrics]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportingMetrics](
	[MetricID] [int] IDENTITY(1,1) NOT NULL,
	[Code] [nvarchar](64) NOT NULL,
	[SourceId] [nvarchar](64) NOT NULL,
	[Label] [nvarchar](120) NOT NULL,
	[Aggregation] [nvarchar](16) NOT NULL,
	[BaseField] [nvarchar](128) NULL,
	[FilterJson] [nvarchar](max) NULL,
	[Description] [nvarchar](512) NULL,
	[Format] [nvarchar](16) NULL,
	[Enabled] [bit] NOT NULL,
	[SortOrder] [int] NOT NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NOT NULL,
	[GermanLabel] [nvarchar](120) NULL,
	[FrenchLabel] [nvarchar](120) NULL,
	[ItalianLabel] [nvarchar](120) NULL,
	[TotalMode] [nvarchar](16) NOT NULL,
	[DateAnchor] [nvarchar](32) NULL,
 CONSTRAINT [PK_ReportingMetrics] PRIMARY KEY CLUSTERED 
(
	[MetricID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
 CONSTRAINT [UQ_ReportingMetrics_Code] UNIQUE NONCLUSTERED 
(
	[Code] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportingMetrics] ADD  CONSTRAINT [DF_ReportingMetrics_Enabled]  DEFAULT ((1)) FOR [Enabled]
GO
ALTER TABLE [dbo].[ReportingMetrics] ADD  CONSTRAINT [DF_ReportingMetrics_SortOrder]  DEFAULT ((100)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[ReportingMetrics] ADD  CONSTRAINT [DF_ReportingMetrics_CreatedAt]  DEFAULT (sysutcdatetime()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ReportingMetrics] ADD  CONSTRAINT [DF_ReportingMetrics_UpdatedAt]  DEFAULT (sysutcdatetime()) FOR [UpdatedAt]
GO
ALTER TABLE [dbo].[ReportingMetrics] ADD  CONSTRAINT [DF_ReportingMetrics_TotalMode]  DEFAULT ('sum') FOR [TotalMode]
GO
ALTER TABLE [dbo].[ReportingMetrics]  WITH CHECK ADD  CONSTRAINT [CK_ReportingMetrics_Aggregation] CHECK  (([Aggregation]='max' OR [Aggregation]='min' OR [Aggregation]='avg' OR [Aggregation]='sum' OR [Aggregation]='count_distinct' OR [Aggregation]='count'))
GO
ALTER TABLE [dbo].[ReportingMetrics] CHECK CONSTRAINT [CK_ReportingMetrics_Aggregation]
GO
ALTER TABLE [dbo].[ReportingMetrics]  WITH CHECK ADD  CONSTRAINT [CK_ReportingMetrics_TotalMode] CHECK  (([TotalMode]='latest' OR [TotalMode]='sum'))
GO
ALTER TABLE [dbo].[ReportingMetrics] CHECK CONSTRAINT [CK_ReportingMetrics_TotalMode]
GO
