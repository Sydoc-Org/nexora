USE [nexora]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[StatConfig](
	[ProcessName] [nvarchar](100) NULL,
	[TableName] [nvarchar](100) NULL,
	[ExportColumn] [nvarchar](100) NULL,
	[additionalCondition] [nvarchar](100) NULL,
	[ImportColumn] [nvarchar](50) NULL
) ON [PRIMARY]
GO

