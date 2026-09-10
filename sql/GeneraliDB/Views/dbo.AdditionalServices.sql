USE [Generali]
GO
DROP VIEW [dbo].[AdditionalServices]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[AdditionalServices] AS
SELECT ID, SubCategory, ParentCategory
FROM dbo.EffortCategories;

GO
