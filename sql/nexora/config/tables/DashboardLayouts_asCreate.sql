USE [nexora]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[FieldMetadata](
	[FieldKey] [varchar](100) NOT NULL,
	[DataType] [varchar](20) NOT NULL,
	[Aggregable] [bit] NOT NULL,
	[Sortable] [bit] NOT NULL,
 CONSTRAINT [PK_FieldMetadata] PRIMARY KEY CLUSTERED 
(
	[FieldKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[FieldMetadata] ADD  CONSTRAINT [DF_FieldMetadata_Aggregable]  DEFAULT ((0)) FOR [Aggregable]
GO

ALTER TABLE [dbo].[FieldMetadata] ADD  CONSTRAINT [DF_FieldMetadata_Sortable]  DEFAULT ((1)) FOR [Sortable]
GO

ALTER TABLE [dbo].[FieldMetadata]  WITH CHECK ADD  CONSTRAINT [CK_FieldMetadata_DataType] CHECK  (([DataType]='text' OR [DataType]='date' OR [DataType]='categorical' OR [DataType]='numeric'))
GO

ALTER TABLE [dbo].[FieldMetadata] CHECK CONSTRAINT [CK_FieldMetadata_DataType]
GO


