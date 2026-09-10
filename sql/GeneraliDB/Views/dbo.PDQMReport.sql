USE [Generali]
GO
DROP VIEW [dbo].[PDQMReport]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[PDQMReport] AS
SELECT ID, Quantity, ForDate, UserID, RecordDateTime, ParentCategory, ParentSubCategory, SubCategory
FROM dbo.QualityCheckEntries;

GO
