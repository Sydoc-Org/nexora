-- 0135_seed_privera_posteingang_source.sql
-- Privera Posteingang, from AES Sprint 54 (#329) -- the sixth and last of the
-- monthly workbooks. Replaces
-- R:\...\Privera\01_Posteingang\Statistik\Privera-Statistik_TP01-Posteingang-<YYYYMM>.xlsx
-- with a source over 01_Privera_Posteingang.dbo.Reporting_P1_Dokumente.
--
-- WHAT THE OLD REPORT IS
-- One pivot: rows Register, columns Niederlassung, page filter ExportDatetime,
-- a single data field "Anzahl von Barcode". August 2026 published 10,044.
--
-- THE DATE COLUMN IS TEXT, AND THAT SHAPES EVERYTHING BELOW
-- ExportDatetime is nvarchar holding 'dd.MM.yyyy HH:mm:ss'. It cannot be
-- declared a date here. Our connection runs us_english, so asking SQL Server to
-- read it as one gives:
--     '01.02.2021' (1 February)  -> year 2021, MONTH 1   -- silently wrong
--     '25.08.2026' (day > 12)    -> Conversion failed    -- the query errors
-- Both measured against PROD, not assumed. So most months would fail outright
-- and the survivors would be wrong -- the worst combination for a billing
-- figure.
--
-- SO THE COLUMN IS EXPOSED AS A STRING
-- Picking a month is a `contains` filter on 'Export date (text)': `.08.2026`
-- renders as LIKE '%.08.2026%' and returns exactly the published 10,044,
-- verified. That is the same shape as the workbook, which is one file per month
-- with the month ticked in a filter -- so nothing is lost against what this
-- replaces.
--
-- WHAT IS LOST, AND HOW TO GET IT BACK
-- No month grain, so no monthly series or chart over time: grouping needs a
-- real date. The fix belongs in the source database, not here. Reporting_P1_Dokumente
-- is a VIEW, so it is one added column, no table change and no back-fill:
--     TRY_CONVERT(datetime, ExportDatetime, 104) AS ExportDatetime_dt
-- (104 is day-first German; TRY_CONVERT yields NULL rather than failing on a
-- malformed row). That expression returns exactly 10,044 for August too. Once
-- the column exists, add it to ColumnsJSON as a grainable date and this source
-- gains the grain with no other change. Tracked on #329.
--
-- WHY NOT TEACH THE REPORTING LAYER TO PARSE TEXT DATES
-- It was considered. It would mean wrapping every reference to the column --
-- select, group by, where, order by -- in a conversion, in code every source
-- shares, to accommodate one column in one view; and it would defeat any index
-- on 858k rows. A view column is cheaper, correct at the source, and helps
-- every other tool reading that view.
--
-- PROPERTY AND RECIPIENT COLUMNS ARE NOT EXPOSED
-- Same call as 0132: EigentuemerNr, LiegenschaftsNr, MietverhaeltnisNr and
-- Empfaenger identify a property, its owner, a tenancy and a named recipient.
-- Counting documents needs none of them.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.privera_posteingang.use', N'Use the Privera Posteingang source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.privera_posteingang.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'privera_posteingang')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'privera_posteingang', 'curated', N'Privera — Posteingang',
    'reporting.source.privera_posteingang.use', 'statistics', 'table',
    '01_Privera_Posteingang.dbo.Reporting_P1_Dokumente',
    N'[{"field":"ExportDatetime","label":"Export date (text)","type":"string","filterable":true,"sortable":true},
       {"field":"Register","label":"Register","type":"string","filterable":true,"sortable":true},
       {"field":"Niederlassung","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"Dokumenttyp","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"DossierTyp","label":"Dossier type","type":"string","filterable":true,"sortable":true},
       {"field":"Abteilung","label":"Department","type":"string","filterable":true,"sortable":true},
       {"field":"Art","label":"Kind","type":"string","filterable":true,"sortable":true},
       {"field":"Nachsendung","label":"Forwarding","type":"string","filterable":true,"sortable":true},
       {"field":"Einschreiben","label":"Registered post","type":"string","filterable":true,"sortable":true},
       {"field":"Vertraulichkeit","label":"Confidentiality","type":"string","filterable":true,"sortable":true},
       {"field":"ScanSource","label":"Scan source","type":"string","filterable":true,"sortable":true},
       {"field":"ScanUser","label":"Scan user","type":"string","filterable":true,"sortable":true},
       {"field":"ValUser","label":"Validation user","type":"string","filterable":true,"sortable":true},
       {"field":"AnzahlImagesScanned","label":"Images scanned","type":"number","filterable":true,"sortable":true},
       {"field":"AnzahlImagesProcessed","label":"Images processed","type":"number","filterable":true,"sortable":true},
       {"field":"DokumentRescanAm","label":"Rescanned at","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"DokumentGeloeschtAm","label":"Deleted at","type":"date","filterable":true,"sortable":true,"grainable":true}]',
    1, 380);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('privera_posteingang_documents', 'privera_posteingang',
        N'Documents', N'Dokumente', N'Documents', N'Documenti',
        'count', NULL, NULL,
        N'The billed figure, the workbook''s "Anzahl von Barcode". Pick a month with a contains filter on Export date (text) -- e.g. .08.2026 -- because that column is text, not a date, so it cannot be grouped by month. Group by Register and Branch for the workbook''s layout.', 'int', 380)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
