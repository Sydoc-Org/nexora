USE [Generali]
GO
DROP VIEW [dbo].[ReportingISS]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[ReportingISS] AS
SELECT ID, ReportForDate, ReportTimeStamp, ReportByUserID, OnTime, Category AS category
FROM dbo.IssReports;

GO
