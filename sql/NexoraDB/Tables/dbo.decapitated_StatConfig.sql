USE [nexora]
GO
ALTER TABLE [dbo].[decapitated_StatConfig] DROP CONSTRAINT [DF_Statconfig_ClientCode]
GO
DROP TABLE [dbo].[decapitated_StatConfig]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[decapitated_StatConfig](
	[ProcessName] [nvarchar](100) NOT NULL,
	[TableName] [nvarchar](100) NULL,
	[ExportColumn] [nvarchar](100) NULL,
	[additionalCondition] [nvarchar](100) NULL,
	[ImportColumn] [nvarchar](50) NULL,
	[WorkitemColumn] [nvarchar](100) NULL,
	[ClientCode] [nvarchar](50) NOT NULL,
 CONSTRAINT [PK_StatConfig] PRIMARY KEY CLUSTERED 
(
	[ProcessName] ASC,
	[ClientCode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[decapitated_StatConfig] ADD  CONSTRAINT [DF_Statconfig_ClientCode]  DEFAULT ('default') FOR [ClientCode]
GO
