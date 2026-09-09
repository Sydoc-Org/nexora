-- 0119_generali_documents_source_and_labels.sql
-- The Generali dashboard reads dbo.v_ReportJobJoinDefinitions (the ReportJob
-- document feed with every lookup label joined in, ~870k rows) and the import
-- status page reads dbo.CSVImportLog. Neither was a reporting source. Register
-- both through the 'table' provider and give them wizard measures. Also relabel
-- the ISS source to "Reporting" (matches the tenant page name): the wizard now
-- groups "Generali — X" labels under one Generali heading. Idempotent.

UPDATE dbo.ReportingSources SET Label = N'Generali — Reporting', UpdatedAt = SYSUTCDATETIME()
WHERE Code = 'generali_iss' AND Label <> N'Generali — Reporting';
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    (N'reporting.source.generali_documents.use', N'Use the Generali Documents source'),
    (N'reporting.source.generali_imports.use',   N'Use the Generali CSV Imports source')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

-- Curated column subset of the view: the dimensions the dashboard charts plus
-- the dates and the couvert doc count. Free-text and SAP/partner-number
-- columns stay out; /reporting/sources can expose more.
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_documents')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_documents', 'curated', N'Generali — Documents',
    'reporting.source.generali_documents.use', 'generali', 'table', 'dbo.v_ReportJobJoinDefinitions',
    N'[{"field":"DOC_SCANDATUM","label":"Scan date","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"DOC_DateCreated","label":"Created","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"DOC_DOKUMENTENTYP","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_EINGANGSKANAL","label":"Input channel","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_KOMMUNIKATION","label":"Communication","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_RICHTUNG","label":"Direction","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_EMPFAENGER","label":"Recipient","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_SPRACHE","label":"Language","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_DOKUMENTENSTATUS","label":"Document status","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_NOTIFIKATIONSSTATUS","label":"Notification status","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_SCANORT","label":"Scan location","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_ORIGIN","label":"Origin","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_NK1","label":"Post-check 1","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_NK2","label":"Post-check 2","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_SCANUSER","label":"Scan user","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_INITIAL_USER","label":"Initial user","type":"string","filterable":true,"sortable":true},
       {"field":"DOC_COUVERTDOCCOUNT","label":"Documents in couvert","type":"number","filterable":true,"sortable":true},
       {"field":"DOC_ID","label":"Document ID","type":"string","filterable":true,"sortable":true},
       {"field":"CASE_ID","label":"Case ID","type":"string","filterable":true,"sortable":true}]',
    1, 20);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_imports')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_imports', 'curated', N'Generali — CSV Imports',
    'reporting.source.generali_imports.use', 'generali', 'table', 'dbo.CSVImportLog',
    N'[{"field":"StartedAt","label":"Started","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"FinishedAt","label":"Finished","type":"datetime","filterable":true,"sortable":true},
       {"field":"FileName","label":"File","type":"string","filterable":true,"sortable":true},
       {"field":"Status","label":"Status","type":"string","filterable":true,"sortable":true},
       {"field":"CSVRowCount","label":"CSV rows","type":"number","filterable":true,"sortable":true},
       {"field":"RowsInserted","label":"Rows inserted","type":"number","filterable":true,"sortable":true},
       {"field":"RowsUpdated","label":"Rows updated","type":"number","filterable":true,"sortable":true},
       {"field":"MinScanDatum","label":"Earliest scan date","type":"datetime","filterable":true,"sortable":true},
       {"field":"MaxScanDatum","label":"Latest scan date","type":"datetime","filterable":true,"sortable":true}]',
    1, 25);
GO

-- Order: the platform sources first (docprocessing has no row and sorts at the
-- code default 100), then the Generali block with Documents leading and PDQM
-- after the effort tables. The wizard walks sources in this order.
UPDATE s SET s.SortOrder = v.SortOrder
FROM dbo.ReportingSources s
JOIN (VALUES
    ('field_quality', 110),
    ('generali_documents', 200), ('generali_attendance', 201), ('generali_baseservices', 202),
    ('generali_projects', 203), ('generali_iss', 204), ('generali_imports', 205), ('generali_pdqm', 206)
) AS v(Code, SortOrder) ON v.Code = s.Code
WHERE s.SortOrder <> v.SortOrder;
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('generali_documents_count', 'generali_documents', N'Documents', N'Dokumente', N'Documents', N'Documenti',
        'count', NULL, N'Number of Generali documents (ReportJob rows)', 'int', 100),
    ('generali_documents_cases', 'generali_documents', N'Cases', N'Fälle', N'Dossiers', N'Casi',
        'count_distinct', 'CASE_ID', N'Number of distinct cases', 'int', 101),
    ('generali_imports_runs',     'generali_imports', N'Import runs',   N'Importläufe',        N'Exécutions d''import', N'Esecuzioni import',
        'count', NULL,          N'Number of CSV import runs', 'int', 150),
    ('generali_imports_inserted', 'generali_imports', N'Rows inserted', N'Eingefügte Zeilen',  N'Lignes insérées',      N'Righe inserite',
        'sum',   'RowsInserted', N'Rows inserted by CSV imports', 'int', 151),
    ('generali_imports_updated',  'generali_imports', N'Rows updated',  N'Aktualisierte Zeilen', N'Lignes mises à jour', N'Righe aggiornate',
        'sum',   'RowsUpdated',  N'Rows updated by CSV imports', 'int', 152)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
