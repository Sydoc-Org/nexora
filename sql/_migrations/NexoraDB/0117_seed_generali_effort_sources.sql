-- 0117_seed_generali_effort_sources.sql
-- Generali had one reporting source (PDQM, migration 0011) while four more fact
-- tables sat unreported. Register them through the generic 'table' provider --
-- ColumnsJSON is the whole "process config" a custom tenant needs, no code:
--   * generali_attendance  -> dbo.Attendance         (effort by parent/sub category)
--   * generali_baseservices -> dbo.BaseServices      (effort by category)
--   * generali_projects    -> dbo.ProjectManagement  (effort by category, with comment)
--   * generali_iss         -> dbo.ReportingISS       (KPI reports filed, on-time flag)
-- Lookup tables (AdditionalServices, Nachkontrolle, Kommunikation) carry no
-- measures and are not registered; /reporting/sources can add them any time.
-- Permissions follow the reporting.source.<code>.use grammar (0088); the
-- Enterprise Admin trigger (0106) grants them, nobody else gets them implicitly.
-- Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    (N'reporting.source.generali_attendance.use',   N'Use the Generali Attendance source'),
    (N'reporting.source.generali_baseservices.use', N'Use the Generali Base Services source'),
    (N'reporting.source.generali_projects.use',     N'Use the Generali Project Management source'),
    (N'reporting.source.generali_iss.use',          N'Use the Generali ISS Reporting source')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_attendance')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_attendance', 'curated', N'Generali — Attendance',
    'reporting.source.generali_attendance.use', 'generali', 'table', 'dbo.Attendance',
    N'[{"field":"ForDate","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ParentCategory","label":"Parent category","type":"string","filterable":true,"sortable":true},
       {"field":"SubCategory","label":"Subcategory","type":"string","filterable":true,"sortable":true},
       {"field":"EffortInHours","label":"Effort (hours)","type":"number","filterable":true,"sortable":true},
       {"field":"UserID","label":"User ID","type":"number","filterable":true,"sortable":true},
       {"field":"RecordDateTime","label":"Recorded at","type":"datetime","filterable":true,"sortable":true,"grainable":true}]',
    1, 21);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_baseservices')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_baseservices', 'curated', N'Generali — Base Services',
    'reporting.source.generali_baseservices.use', 'generali', 'table', 'dbo.BaseServices',
    N'[{"field":"ForDate","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Category","label":"Category","type":"string","filterable":true,"sortable":true},
       {"field":"EffortInHours","label":"Effort (hours)","type":"number","filterable":true,"sortable":true},
       {"field":"UserID","label":"User ID","type":"number","filterable":true,"sortable":true},
       {"field":"RecordDateTime","label":"Recorded at","type":"datetime","filterable":true,"sortable":true,"grainable":true}]',
    1, 22);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_projects')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_projects', 'curated', N'Generali — Project Management',
    'reporting.source.generali_projects.use', 'generali', 'table', 'dbo.ProjectManagement',
    N'[{"field":"ForDate","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Category","label":"Category","type":"string","filterable":true,"sortable":true},
       {"field":"EffortInHours","label":"Effort (hours)","type":"number","filterable":true,"sortable":true},
       {"field":"Comment","label":"Comment","type":"string","filterable":false,"sortable":false},
       {"field":"UserID","label":"User ID","type":"number","filterable":true,"sortable":true},
       {"field":"RecordDateTime","label":"Recorded at","type":"datetime","filterable":true,"sortable":true,"grainable":true}]',
    1, 23);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_iss')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_iss', 'curated', N'Generali — ISS Reporting',
    'reporting.source.generali_iss.use', 'generali', 'table', 'dbo.ReportingISS',
    N'[{"field":"ReportForDate","label":"Report date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"category","label":"KPI category","type":"string","filterable":true,"sortable":true},
       {"field":"OnTime","label":"On time (1/0)","type":"number","filterable":true,"sortable":true},
       {"field":"ReportByUserID","label":"Reported by (user ID)","type":"number","filterable":true,"sortable":true},
       {"field":"ReportTimeStamp","label":"Reported at","type":"datetime","filterable":true,"sortable":true,"grainable":true}]',
    1, 24);
GO
