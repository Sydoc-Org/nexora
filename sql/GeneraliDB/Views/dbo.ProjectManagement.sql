USE [Generali]
GO
DROP VIEW [dbo].[ProjectManagement]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE   VIEW [dbo].[ProjectManagement] AS
SELECT ID, EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime
FROM dbo.ProjectEntries;

GO
