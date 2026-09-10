USE [Generali]
GO
DROP VIEW [dbo].[PDQMMapping]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[PDQMMapping] AS
SELECT ID, ParentCategory, ParentSubCategory, SubCategory
FROM dbo.QualityCheckCategories;

GO
