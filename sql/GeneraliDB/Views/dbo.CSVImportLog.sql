USE [Generali]
GO
DROP VIEW [dbo].[CSVImportLog]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[CSVImportLog] AS
SELECT ID, FileName, StartedAt, FinishedAt, CSVRowCount, RowsInserted, RowsUpdated,
       MinScannedAt AS MinScanDatum, MaxScannedAt AS MaxScanDatum, [Status]
FROM dbo.ImportRuns;

GO
