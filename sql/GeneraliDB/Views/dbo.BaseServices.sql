USE [Generali]
GO
DROP VIEW [dbo].[BaseServices]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[BaseServices] AS
SELECT ID, EffortInHours, UserID, ForDate, Category, RecordDateTime
FROM dbo.BaseServiceEntries;

GO
