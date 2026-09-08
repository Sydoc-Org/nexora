-- 0118_seed_generali_measures.sql
-- The Simple wizard lists measures grouped by source, so a source without a
-- ReportingMetrics row never appears there (Advanced only). Give the four
-- Generali sources from 0117 their measures: effort hours + entry count for the
-- three effort tables, reports filed + on-time count for ISS. Idempotent.

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('generali_attendance_hours',   'generali_attendance',   N'Effort (hours)', N'Aufwand (Stunden)', N'Effort (heures)', N'Impegno (ore)',
        'sum',   'EffortInHours', N'Sum of attendance effort hours', NULL,  110),
    ('generali_attendance_entries', 'generali_attendance',   N'Entries',        N'Einträge',          N'Entrées',         N'Voci',
        'count', NULL,            N'Number of attendance entries',   'int', 111),
    ('generali_baseservices_hours',   'generali_baseservices', N'Effort (hours)', N'Aufwand (Stunden)', N'Effort (heures)', N'Impegno (ore)',
        'sum',   'EffortInHours', N'Sum of base-service effort hours', NULL,  120),
    ('generali_baseservices_entries', 'generali_baseservices', N'Entries',        N'Einträge',          N'Entrées',         N'Voci',
        'count', NULL,            N'Number of base-service entries',   'int', 121),
    ('generali_projects_hours',   'generali_projects', N'Effort (hours)', N'Aufwand (Stunden)', N'Effort (heures)', N'Impegno (ore)',
        'sum',   'EffortInHours', N'Sum of project-management effort hours', NULL,  130),
    ('generali_projects_entries', 'generali_projects', N'Entries',        N'Einträge',          N'Entrées',         N'Voci',
        'count', NULL,            N'Number of project-management entries',   'int', 131),
    -- no on-time sum: OnTime is a bit and T-SQL refuses SUM over it; break the
    -- count down by the "On time (1/0)" dimension instead.
    ('generali_iss_reports', 'generali_iss', N'Reports filed', N'Eingereichte Reports', N'Rapports déposés', N'Rapporti inviati',
        'count', NULL,     N'Number of ISS KPI reports filed', 'int', 140)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
