USE [Generali]
GO
DROP VIEW [dbo].[Attendance]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- ---------------------------------------------------------------------------
-- 4. Compat views under the old names, for the deploy window only (D8).
--    Single-table, no aggregates, so they stay updatable -- the CRUD endpoints
--    can still INSERT/UPDATE/DELETE through them if a write lands mid-deploy.
--    Phase 6 drops all nine.
-- ---------------------------------------------------------------------------
CREATE   VIEW [dbo].[Attendance] AS
SELECT ID, EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime
FROM dbo.AttendanceEntries;

GO
