USE [Generali]
GO
DROP TABLE [dbo].[QualityCheckCategories]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[QualityCheckCategories](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[ParentCategory] [nvarchar](100) NULL,
	[ParentSubCategory] [nvarchar](100) NULL,
	[SubCategory] [nvarchar](100) NULL,
 CONSTRAINT [PK_QualityCheckCategories] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
