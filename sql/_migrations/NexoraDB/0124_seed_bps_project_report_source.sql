-- 0124_seed_bps_project_report_source.sql
-- The bpsuite "Projektbericht" export now lands in
-- SYDOC_Statistik.dbo.BPS_ProjectReport (C:\dev\nx-sources\bps\bps_project_report.py,
-- one row per booked block: customer / project package / task / date / hours /
-- user). Register it as a generic 'table' source (0117 pattern) with two
-- measures so it shows in the Simple wizard. Permission follows
-- reporting.source.<code>.use (0088); Enterprise Admin only (0106). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.bps_projects.use', N'Use the Sydoc Project Hours (BPS) source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.bps_projects.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'bps_projects')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'bps_projects', 'curated', N'Sydoc — Project Hours',
    'reporting.source.bps_projects.use', 'statistics', 'table', 'dbo.BPS_ProjectReport',
    N'[{"field":"Datum","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Kunde","label":"Customer","type":"string","filterable":true,"sortable":true},
       {"field":"Projektpaket","label":"Project package","type":"string","filterable":true,"sortable":true},
       {"field":"Aufgabe","label":"Task","type":"string","filterable":true,"sortable":true},
       {"field":"Benutzer","label":"User","type":"string","filterable":true,"sortable":true},
       {"field":"Stunden","label":"Hours","type":"number","filterable":true,"sortable":true},
       {"field":"Beschreibung","label":"Description","type":"string","filterable":true,"sortable":false}]',
    1, 120);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('bps_projects_hours', 'bps_projects', N'Hours', N'Stunden', N'Heures', N'Ore',
        'sum', 'Stunden', NULL, N'Sum of booked project hours', NULL, 120),
    ('bps_projects_entries', 'bps_projects', N'Bookings', N'Buchungen', N'Réservations', N'Prenotazioni',
        'count', NULL, NULL, N'Number of booked blocks', 'int', 121),
    ('bps_projects_absence_hours', 'bps_projects', N'Absence hours', N'Abwesenheitsstunden', N'Heures d''absence', N'Ore di assenza',
        'sum', 'Stunden', N'[{"field":"Kunde","op":"eq","value":"Absences"}]', N'Hours booked on the Absences pseudo-customer', NULL, 122)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
