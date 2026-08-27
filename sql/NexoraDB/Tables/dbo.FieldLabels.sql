USE [nexora]
GO
ALTER TABLE [dbo].[FieldLabels] DROP CONSTRAINT [DF_FieldLabels_IsSensitive]
GO
DROP TABLE [dbo].[FieldLabels]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[FieldLabels](
	[FieldKey] [nvarchar](100) NOT NULL,
	[EnglishLabel] [nvarchar](200) NOT NULL,
	[GermanLabel] [nvarchar](200) NULL,
	[FrenchLabel] [nvarchar](200) NULL,
	[ItalianLabel] [nvarchar](200) NULL,
	[IsSensitive] [bit] NOT NULL,
 CONSTRAINT [PK_FieldLabels] PRIMARY KEY CLUSTERED 
(
	[FieldKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[FieldLabels] ADD  CONSTRAINT [DF_FieldLabels_IsSensitive]  DEFAULT ((0)) FOR [IsSensitive]
GO
