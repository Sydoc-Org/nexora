-- 0127_seed_bucherer_frigemo_sources.sql
-- (renumbered from 0123 to clear the collision with 0123_report_annotations)
-- Two Statistics-DB fact tables the collectors already fill but nobody could
-- report on. Register them through the generic 'table' provider (0117 pattern,
-- ColumnsJSON is the whole config, no code):
--   * bucherer_easytax -> SYDOC_Statistik.dbo.Bucherer_EasyTax  (one row per
--     document: import time, export time when it left, page count)
--   * frigemo          -> SYDOC_Statistik.dbo.Frigemo           (one row per
--     day, already-summed import/export/delete counters)
-- Measures (0118 pattern) so both show in the Simple wizard; "Exported" on
-- Bucherer is a conditional count over ExportTime (0120 FilterJson).
-- Permissions follow reporting.source.<code>.use (0088); only the Enterprise
-- Admin trigger (0106) grants them. Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    (N'reporting.source.bucherer_easytax.use', N'Use the Bucherer EasyTax source'),
    (N'reporting.source.frigemo.use',          N'Use the Frigemo Documents source')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'bucherer_easytax')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'bucherer_easytax', 'curated', N'Bucherer — EasyTax',
    'reporting.source.bucherer_easytax.use', 'statistics', 'table', 'dbo.Bucherer_EasyTax',
    N'[{"field":"WorkItemID","label":"Workitem ID","type":"string","filterable":true,"sortable":true},
       {"field":"ImportTime","label":"Imported at","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"ExportTime","label":"Exported at","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"RemoteFileName","label":"Import file","type":"string","filterable":true,"sortable":true},
       {"field":"ExportFileName","label":"Export file","type":"string","filterable":true,"sortable":true},
       {"field":"PageCount","label":"Pages","type":"number","filterable":true,"sortable":true}]',
    1, 300);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'frigemo')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'frigemo', 'curated', N'Frigemo — Documents',
    'reporting.source.frigemo.use', 'statistics', 'table', 'dbo.Frigemo',
    N'[{"field":"Date","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ImportOverallDocs","label":"Imported documents","type":"number","filterable":true,"sortable":true},
       {"field":"ExportOverallDocs","label":"Exported documents","type":"number","filterable":true,"sortable":true},
       {"field":"ImportOverallPages","label":"Imported pages","type":"number","filterable":true,"sortable":true},
       {"field":"ExportOverallPages","label":"Exported pages","type":"number","filterable":true,"sortable":true},
       {"field":"ImportOverallInvoice","label":"Imported invoices","type":"number","filterable":true,"sortable":true},
       {"field":"DeleteOverall","label":"Deleted","type":"number","filterable":true,"sortable":true},
       {"field":"ImportNoReplyMails","label":"No-reply mails","type":"number","filterable":true,"sortable":true},
       {"field":"ImportNoReplyDocs","label":"No-reply documents","type":"number","filterable":true,"sortable":true},
       {"field":"ImportNoReplyPages","label":"No-reply pages","type":"number","filterable":true,"sortable":true}]',
    1, 310);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('bucherer_easytax_imported', 'bucherer_easytax', N'Imported documents', N'Importierte Dokumente', N'Documents importés', N'Documenti importati',
        'count', NULL, NULL, N'Number of EasyTax documents imported (rows)', 'int', 300),
    ('bucherer_easytax_exported', 'bucherer_easytax', N'Exported documents', N'Exportierte Dokumente', N'Documents exportés', N'Documenti esportati',
        'count', NULL, N'[{"field":"ExportTime","op":"is_not_null","value":null}]', N'EasyTax documents with an export time', 'int', 301),
    ('bucherer_easytax_pages', 'bucherer_easytax', N'Pages', N'Seiten', N'Pages', N'Pagine',
        'sum', 'PageCount', NULL, N'Sum of EasyTax page counts', 'int', 302),
    ('frigemo_imported_docs', 'frigemo', N'Imported documents', N'Importierte Dokumente', N'Documents importés', N'Documenti importati',
        'sum', 'ImportOverallDocs', NULL, N'Sum of daily imported documents', 'int', 310),
    ('frigemo_exported_docs', 'frigemo', N'Exported documents', N'Exportierte Dokumente', N'Documents exportés', N'Documenti esportati',
        'sum', 'ExportOverallDocs', NULL, N'Sum of daily exported documents', 'int', 311),
    ('frigemo_imported_pages', 'frigemo', N'Imported pages', N'Importierte Seiten', N'Pages importées', N'Pagine importate',
        'sum', 'ImportOverallPages', NULL, N'Sum of daily imported pages', 'int', 312),
    ('frigemo_exported_pages', 'frigemo', N'Exported pages', N'Exportierte Seiten', N'Pages exportées', N'Pagine esportate',
        'sum', 'ExportOverallPages', NULL, N'Sum of daily exported pages', 'int', 313),
    ('frigemo_deleted', 'frigemo', N'Deleted documents', N'Gelöschte Dokumente', N'Documents supprimés', N'Documenti eliminati',
        'sum', 'DeleteOverall', NULL, N'Sum of daily deleted documents', 'int', 314),
    ('frigemo_invoices', 'frigemo', N'Imported invoices', N'Importierte Rechnungen', N'Factures importées', N'Fatture importate',
        'sum', 'ImportOverallInvoice', NULL, N'Sum of daily imported invoices', 'int', 315)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
