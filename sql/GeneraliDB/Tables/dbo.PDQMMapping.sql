USE [Generali]
GO
DROP TABLE [dbo].[PDQMMapping]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PDQMMapping](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[ParentCategory] [nvarchar](100) NULL,
	[ParentSubCategory] [nvarchar](100) NULL,
	[SubCategory] [nvarchar](100) NULL
) ON [PRIMARY]
GO
