-- 0130_seed_em_invoice_source.sql
-- Elektro-Material ZH monthly billing figures, from AES Sprint 54 (#329):
-- replace the hand-refreshed workbook under
-- R:\...\Elektro-Material_ZH\...\Statistik\Monatsauswertungen\EM-Statistik<YYYYMM>.xlsx
-- with a reporting source over SYDOC_Statistik.dbo.EM_Invoice, which is what
-- that workbook's Power Query already reads.
--
-- WHAT THE OLD REPORT ACTUALLY IS
-- A single pivot: rows = Eingang, page filter = ExportEM, three data fields --
-- "Anzahl von DocBarcode", "Summe von AnzImagesOut", "Summe von OrdItmPosCount".
-- The measures below are those three plus the Opex/e-mail split the pivot shows
-- as its two rows. Read out of the workbook's own pivot definition rather than
-- guessed from the sheet.
--
-- WHY EVERY MEASURE CARRIES THE SAME Eingang FILTER
-- The published total is the sum of the pivot's two rows, OPEX + E_MAIL. Over
-- the whole table Eingang also takes 'Nexora' (3 rows) and NULL (286), so an
-- unfiltered SUM would quietly bill rows the workbook never counted. The
-- filter makes the totals mean "Opex + e-mail" in every month, including one
-- where a stray channel appears. Conditional aggregation is the 0128 pattern.
--
-- WHY ExportEM_dt AND NOT ExportEM
-- Both exist and agree where both are set, but ExportEM is nvarchar holding
-- 'dd.mm.yyyy HH:MM:SS' -- unsortable, ungrainable, and the reason the old
-- report needs a human to tick the right timestamps out of a filter list every
-- month. ExportEM_dt is a real datetime and covers more rows.
--
-- THE AMOUNT COLUMNS ARE DELIBERATELY NOT EXPOSED
-- EM_Invoice carries GrossAmount/NetAmount/VatAmount, BankIBAN, SPC_IBAN,
-- CrdNO and creditor names. None of it is needed to bill scan volume, so it is
-- left out of ColumnsJSON: a column that is not in the catalogue cannot be
-- selected, filtered or sorted by anyone holding the permission.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.em_invoice.use', N'Use the Elektro-Material billing source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.em_invoice.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'em_invoice')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'em_invoice', 'curated', N'Elektro-Material — Verrechnung',
    'reporting.source.em_invoice.use', 'statistics', 'table', 'dbo.EM_Invoice',
    N'[{"field":"ExportEM_dt","label":"Export date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Eingang","label":"Channel","type":"string","filterable":true,"sortable":true},
       {"field":"DocBarcode","label":"Document barcode","type":"string","filterable":true,"sortable":true},
       {"field":"DocType","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"DocDate","label":"Document date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"OrdItmPosCount","label":"Order item positions","type":"number","filterable":true,"sortable":true},
       {"field":"AnzImagesOut","label":"Images out","type":"number","filterable":true,"sortable":true},
       {"field":"AnzImagesIn","label":"Images in","type":"number","filterable":true,"sortable":true},
       {"field":"IsWithOrder","label":"With order","type":"string","filterable":true,"sortable":true},
       {"field":"isExpress","label":"Express","type":"string","filterable":true,"sortable":true},
       {"field":"Branch","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"ScanUser","label":"Scan user","type":"string","filterable":true,"sortable":true},
       {"field":"ValUser","label":"Validation user","type":"string","filterable":true,"sortable":true}]',
    1, 330);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('em_documents', 'em_invoice',
        N'Documents (Opex + e-mail)', N'Dokumente (Opex + E-Mail)', N'Documents (Opex + e-mail)', N'Documenti (Opex + e-mail)',
        'count', NULL, N'[{"field":"Eingang","op":"in","value":["OPEX Scan Scanner","E_MAIL"]}]',
        N'Total document barcodes billed for the period, both intake channels. Matches the pivot''s Gesamtergebnis for "Anzahl von DocBarcode".', 'int', 330),
    ('em_opex_scans', 'em_invoice',
        N'Opex scans', N'Opex-Scans', N'Scans Opex', N'Scansioni Opex',
        'count', NULL, N'[{"field":"Eingang","op":"eq","value":"OPEX Scan Scanner"}]',
        N'Documents that came in on the Opex scanner rather than by e-mail.', 'int', 331),
    ('em_email_documents', 'em_invoice',
        N'E-mail documents', N'E-Mail-Dokumente', N'Documents par e-mail', N'Documenti via e-mail',
        'count', NULL, N'[{"field":"Eingang","op":"eq","value":"E_MAIL"}]',
        N'Documents that arrived by e-mail. The other half of the Opex/e-mail split.', 'int', 332),
    ('em_order_positions', 'em_invoice',
        N'Order item positions', N'Bestellpositionen', N'Postes de commande', N'Posizioni d''ordine',
        'sum', 'OrdItmPosCount', N'[{"field":"Eingang","op":"in","value":["OPEX Scan Scanner","E_MAIL"]}]',
        N'Sum of OrdItmPosCount over both channels -- the pivot''s "Summe von OrdItmPosCount".', 'int', 333),
    ('em_images_out', 'em_invoice',
        N'Images out', N'Ausgegebene Bilder', N'Images sorties', N'Immagini in uscita',
        'sum', 'AnzImagesOut', N'[{"field":"Eingang","op":"in","value":["OPEX Scan Scanner","E_MAIL"]}]',
        N'Sum of AnzImagesOut over both channels -- the pivot''s "Summe von AnzImagesOut".', 'int', 334)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
