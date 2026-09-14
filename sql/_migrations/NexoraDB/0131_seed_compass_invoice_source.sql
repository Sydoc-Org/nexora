-- 0131_seed_compass_invoice_source.sql
-- Compass Group monthly billing figures, from AES Sprint 54 (#329), following
-- 0130 (Elektro-Material). Replaces the hand-refreshed
-- R:\...\CompassGroup\01_PosteingangKreditoren\Verrechnung\CompassGroupVerrechnung<YYYYMM>.xlsx
-- with a source over SYDOC_Statistik.dbo.Compass_Invoice, which is what that
-- workbook's Power Query already reads.
--
-- WHAT THE OLD REPORT IS
-- One pivot, and a simpler one than Elektro-Material's: a single data field,
-- "Anzahl von DocBarcode", with UploadDatetime as the page filter and DocDate
-- (auto-grouped by Excel into Jahre/Quartale/month) as the rows. So the billed
-- figure is a plain document count for the upload month; the DocDate breakdown
-- is detail, not a second measure.
--
-- THE PERIOD IS UploadDatetime, NOT DocDate
-- Worth stating because the pivot's rows are DocDate and that is the eye-catching
-- part. Documents uploaded in one month carry document dates spread over years --
-- the May 2026 workbook shows rows under 2022, 2024 and 2025, plus 235 with no
-- usable DocDate at all. Counting by DocDate would bill a different set entirely.
-- Verified: UploadDatetime in May 2026 gives exactly the published 9,185.
--
-- NO CHANNEL FILTER HERE, UNLIKE 0130
-- Elektro-Material's measures all filter Eingang to the two billed channels,
-- because its pivot totalled two channel rows. This pivot has no such split and
-- its unfiltered count reproduces the published total exactly, so adding a filter
-- "for consistency" with 0130 would change the number. Compass_Invoice does have
-- an Eingang column; it stays a dimension, not a filter.
--
-- AMOUNT AND BANK COLUMNS ARE NOT EXPOSED
-- Same call as 0130: GrossAmount/NetAmount/VatAmount, SPC_IBAN, BankPK, CrdNO,
-- CRDNAME1 and InvoiceNR are not needed to bill document volume, so they are left
-- out of ColumnsJSON and cannot be selected, filtered or sorted.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.compass_invoice.use', N'Use the Compass Group billing source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.compass_invoice.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'compass_invoice')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'compass_invoice', 'curated', N'Compass Group — Verrechnung',
    'reporting.source.compass_invoice.use', 'statistics', 'table', 'dbo.Compass_Invoice',
    N'[{"field":"UploadDatetime","label":"Upload date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"DocDate","label":"Document date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ImportDate","label":"Import date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ExportDate","label":"Export date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"DocBarcode","label":"Document barcode","type":"string","filterable":true,"sortable":true},
       {"field":"DocType","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"Mandat","label":"Mandate","type":"string","filterable":true,"sortable":true},
       {"field":"Eingang","label":"Channel","type":"string","filterable":true,"sortable":true},
       {"field":"IsWithOrder","label":"With order","type":"string","filterable":true,"sortable":true},
       {"field":"Branch","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"ScanUser","label":"Scan user","type":"string","filterable":true,"sortable":true},
       {"field":"OrdItmPosCount","label":"Order item positions","type":"number","filterable":true,"sortable":true},
       {"field":"AnzImagesOut","label":"Images out","type":"number","filterable":true,"sortable":true}]',
    1, 340);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('compass_documents', 'compass_invoice',
        N'Documents', N'Dokumente', N'Documents', N'Documenti',
        'count', NULL, NULL,
        N'The billed figure: one per document barcode. Group by Upload date to get the month the Verrechnung invoices -- the workbook''s "Anzahl von DocBarcode".', 'int', 340)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
