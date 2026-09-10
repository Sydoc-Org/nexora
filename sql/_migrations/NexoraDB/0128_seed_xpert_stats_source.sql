-- 0128_seed_xpert_stats_source.sql
-- Daily Aveniq/xpert DPSI counts land in SYDOC_Statistik.dbo.Xpert_Stats
-- (pushed by mail from the Aveniq box, imported by nx-sources/xpert/
-- importCSVtoSQL.py): one row per day / DPSI database / metric, long format,
-- with the ZHAW breakdowns carrying a Dimension value. Register it as a generic
-- 'table' source (0117 pattern). Measures are conditional sums on Metric so
-- the subset metrics (BFH new creditors, ZHAW breakdowns) never double-count
-- into the total. Permission follows reporting.source.<code>.use (0088);
-- Enterprise Admin only (0106). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.xpert_stats.use', N'Use the Aveniq Xpert Statistics source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.xpert_stats.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'xpert_stats')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'xpert_stats', 'curated', N'Aveniq — Xpert Statistics',
    'reporting.source.xpert_stats.use', 'statistics', 'table', 'dbo.Xpert_Stats',
    N'[{"field":"ExportDate","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Client","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"SourceDb","label":"Source database","type":"string","filterable":true,"sortable":true},
       {"field":"Metric","label":"Metric","type":"string","filterable":true,"sortable":true},
       {"field":"Dimension","label":"Dimension","type":"string","filterable":true,"sortable":true},
       {"field":"Cnt","label":"Count","type":"number","filterable":true,"sortable":true}]',
    1, 320);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('xpert_stats_documents', 'xpert_stats', N'Documents', N'Dokumente', N'Documents', N'Documenti',
        'sum', 'Cnt', N'[{"field":"Metric","op":"eq","value":"Total"}]',
        N'Documents processed per day (the Total metric of every DPSI database)', 'int', 320),
    ('xpert_stats_bfh_new_creditors', 'xpert_stats', N'BFH new creditors', N'BFH neue Kreditoren', N'BFH nouveaux créanciers', N'BFH nuovi creditori',
        'sum', 'Cnt', N'[{"field":"Metric","op":"eq","value":"NeueKreditoren"}]',
        N'BFH documents with the placeholder creditor 9999999999', 'int', 321),
    ('xpert_stats_zhaw_workitems', 'xpert_stats', N'ZHAW workitems', N'ZHAW Workitems', N'ZHAW workitems', N'ZHAW workitem',
        'sum', 'Cnt', N'[{"field":"Metric","op":"eq","value":"WorkItems"}]',
        N'ZHAW Stat_ZHAW rows with a workitem id', 'int', 322)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
