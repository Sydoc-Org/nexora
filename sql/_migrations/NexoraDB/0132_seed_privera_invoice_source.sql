-- 0132_seed_privera_invoice_source.sql
-- Privera Rechnungseingang monthly billing figures, from AES Sprint 54 (#329),
-- following 0130/0131. Replaces
-- R:\...\Privera\01_Posteingang\Statistik\Privera-Invoice-Mandant-<YYYY>-<Monat>.xlsx
-- with a source over SYDOC_Statistik.dbo.PriveraInvoice, the table that
-- workbook's Power Query already reads.
--
-- WHAT THE OLD REPORT IS
-- Three pivots, all counting Barcode by Mandant with ExportDate as the page
-- filter, published as "PRIVERA Invoice gesamt", "... Mail" and "... eBill".
-- Hence three measures rather than one.
--
-- HOW THE MAIL/eBILL SPLIT IS DONE HERE
-- The workbook splits them with a FileName page filter -- a list of ticked file
-- names, which is neither reproducible nor meaningful. DocSource carries the
-- same classification as data: MAIL / SCANINVOICE / POSTEINGANG / eBill, and
-- those four partition the month exactly (11,764 + 5,310 + 135 + 13 = 17,222 for
-- August 2026). So the measures key on DocSource.
--
-- ONE KNOWN DIFFERENCE, DELIBERATELY NOT PAPERED OVER
-- Verified against the published July and August 2026 workbooks: gesamt and
-- eBill match exactly in both months, and Mail matches exactly in July. In
-- August, DocSource='MAIL' gives 11,764 against a published 11,759. The five
-- extra rows are MAIL documents with no Mandant, which the workbook's Mail pivot
-- dropped while its gesamt pivot counted them (the 612 "(Leer)" row). That is an
-- inconsistency in the old report, not a billing rule, so the measure here is the
-- honest "arrived by mail" definition and Mandant stays a dimension -- anyone who
-- wants the old behaviour can exclude the blanks, and it is one filter, not a
-- silent rule welded into the metric. Flagged on #329 for invoicing to settle.
--
-- AMOUNT, BANK AND PROPERTY COLUMNS ARE NOT EXPOSED
-- Same call as 0130/0131, and PriveraInvoice carries more than most: amounts,
-- IBAN, ESR, creditor number and name, plus LiegenschaftsNr/EigentuemerNr, which
-- identify a property and its owner. None of it is needed to bill document
-- volume, so none of it is in ColumnsJSON.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.privera_invoice.use', N'Use the Privera Rechnungseingang billing source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.privera_invoice.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'privera_invoice')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'privera_invoice', 'curated', N'Privera — Rechnungseingang',
    'reporting.source.privera_invoice.use', 'statistics', 'table', 'dbo.PriveraInvoice',
    N'[{"field":"ExportDate","label":"Export date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ScanTime","label":"Scan date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"ImportTime","label":"Import date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Barcode","label":"Barcode","type":"string","filterable":true,"sortable":true},
       {"field":"Mandant","label":"Mandant","type":"string","filterable":true,"sortable":true},
       {"field":"DocSource","label":"Source","type":"string","filterable":true,"sortable":true},
       {"field":"DocType","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"Niederlassung","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"IstwitOrder","label":"With order","type":"string","filterable":true,"sortable":true},
       {"field":"ScanUser","label":"Scan user","type":"string","filterable":true,"sortable":true},
       {"field":"ValUser","label":"Validation user","type":"string","filterable":true,"sortable":true},
       {"field":"AnzImagesScanned","label":"Images scanned","type":"number","filterable":true,"sortable":true},
       {"field":"Reason_no_Export","label":"Reason not exported","type":"string","filterable":true,"sortable":true}]',
    1, 350);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('privera_documents', 'privera_invoice',
        N'Documents total', N'Dokumente gesamt', N'Documents au total', N'Documenti in totale',
        'count', NULL, NULL,
        N'Every invoice document exported in the period, whatever its source -- the workbook''s "PRIVERA Invoice gesamt". Group by Mandant to get its breakdown.', 'int', 350),
    ('privera_mail_documents', 'privera_invoice',
        N'Documents by mail', N'Dokumente per E-Mail', N'Documents par e-mail', N'Documenti via e-mail',
        'count', NULL, N'[{"field":"DocSource","op":"eq","value":"MAIL"}]',
        N'Documents that arrived by mail. The old workbook split this with a FileName filter and dropped mail documents that have no Mandant, so its August 2026 figure was 5 lower than this one.', 'int', 351),
    ('privera_ebill_documents', 'privera_invoice',
        N'eBill documents', N'eBill-Dokumente', N'Documents eBill', N'Documenti eBill',
        'count', NULL, N'[{"field":"DocSource","op":"eq","value":"eBill"}]',
        N'Documents received as eBill -- the workbook''s "PRIVERA Invoice eBill".', 'int', 352)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
