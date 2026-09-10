USE [Generali]
GO
DROP TABLE [dbo].[CategoryTranslations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[CategoryTranslations](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[SourceTable] [nvarchar](50) NULL,
	[OriginalValue] [nvarchar](255) NULL,
	[Locale] [nvarchar](10) NULL,
	[TranslatedValue] [nvarchar](255) NULL,
 CONSTRAINT [PK_CategoryTranslations] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
