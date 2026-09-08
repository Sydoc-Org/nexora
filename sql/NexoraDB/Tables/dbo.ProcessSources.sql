USE [nexora]
GO
DROP TABLE [dbo].[ProcessSources]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ProcessSources](
	[ClientCode] [nvarchar](50) NOT NULL,
	[ProcessName] [nvarchar](100) NOT NULL,
	[TableName] [nvarchar](100) NULL,
	[TableAlias] [nvarchar](10) NULL,
	[JoinCondition] [nvarchar](255) NULL,
	[TimeFilter] [nvarchar](255) NULL,
	[SuggestionTimeFilter] [nvarchar](255) NULL,
	[ExportColumn] [nvarchar](100) NULL,
	[ImportColumn] [nvarchar](100) NULL,
	[WorkitemColumn] [nvarchar](100) NULL,
	[ExtraCondition] [nvarchar](100) NULL,
	[IdColumnType] [nvarchar](30) NULL,
 CONSTRAINT [PK_ProcessSources] PRIMARY KEY CLUSTERED 
(
	[ClientCode] ASC,
	[ProcessName] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
