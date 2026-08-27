USE [nexora]
GO
ALTER TABLE [dbo].[ProcessFieldMappings] DROP CONSTRAINT [FK_ProcessFieldMappings_ProcessSources]
GO
DROP TABLE [dbo].[ProcessFieldMappings]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ProcessFieldMappings](
	[ClientCode] [nvarchar](50) NOT NULL,
	[ProcessName] [nvarchar](100) NOT NULL,
	[FieldKey] [nvarchar](100) NOT NULL,
	[ColumnName] [nvarchar](100) NOT NULL,
	[ColumnType] [nvarchar](30) NULL,
 CONSTRAINT [PK_ProcessFieldMappings] PRIMARY KEY CLUSTERED 
(
	[ClientCode] ASC,
	[ProcessName] ASC,
	[FieldKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ProcessFieldMappings]  WITH CHECK ADD  CONSTRAINT [FK_ProcessFieldMappings_ProcessSources] FOREIGN KEY([ClientCode], [ProcessName])
REFERENCES [dbo].[ProcessSources] ([ClientCode], [ProcessName])
GO
ALTER TABLE [dbo].[ProcessFieldMappings] CHECK CONSTRAINT [FK_ProcessFieldMappings_ProcessSources]
GO
