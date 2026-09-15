-- 0133_seed_privera_nachsendungen_source.sql
-- Privera physische Zustellung (Nachsendungen), from AES Sprint 54 (#329),
-- after 0130-0132. Replaces
-- R:\...\Privera\01_Posteingang\Statistik\Privera-Statistik_TP01-physische Zustellung-<YYYYMM>.xlsx
-- with a source over 01_Privera_Posteingang.dbo.Reporting_P1_Nachsendungen,
-- the table that workbook's Power Query already reads.
--
-- FIRST SOURCE IN ANOTHER DATABASE
-- Every source before this one lives in SYDOC_Statistik, so BaseObject was
-- 'dbo.<table>'. This one is three-part. The engine is unchanged -- it is the
-- same server and the same login, which already has rights here -- but the
-- identifier guard in nx_lib/reporting/table_query.py had to stop refusing a
-- name that starts with a digit before '01_Privera_Posteingang' could be
-- written down at all.
--
-- WHAT THE OLD REPORT IS
-- One pivot: rows = Nachsendungstyp, columns = Niederlassung, a single data
-- field "Anzahl von DokumenttypNr", page filter ExportDatetime. Underneath it,
-- a hand-added line labelled "ohne TEC".
--
-- THE "ohne TEC" LINE IS A REAL RULE, NOT A FUDGE
-- August 2026 published 1,667 total and 1,042 "ohne TEC". 1,667 - 1,042 = 625,
-- which is exactly the "Rechnungen Privera TEC" Nachsendungstyp row. Note it is
-- *not* the TEC Niederlassung column (610) -- that subtraction gives 1,057 and
-- would have been the easy wrong guess. Both figures verified against the
-- workbook, so both are measures here and neither has to be worked out by hand
-- again.
--
-- "Anzahl Seiten" IS NOT EXPOSED
-- The column exists and would be useful, but its name contains a space and the
-- catalogue's field keys must match ^[A-Za-z0-9_]+$ (semantic.py). Exposing it
-- needs the column renamed in the source database or a view over it; it is not
-- worth loosening a validator that guards interpolated SQL.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.privera_nachsendungen.use', N'Use the Privera physical forwarding source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.privera_nachsendungen.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'privera_nachsendungen')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'privera_nachsendungen', 'curated', N'Privera — Physische Zustellung',
    'reporting.source.privera_nachsendungen.use', 'statistics', 'table',
    '01_Privera_Posteingang.dbo.Reporting_P1_Nachsendungen',
    N'[{"field":"ExportDatetime","label":"Export date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"Nachsendungstyp","label":"Forwarding type","type":"string","filterable":true,"sortable":true},
       {"field":"Niederlassung","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"Register","label":"Register","type":"string","filterable":true,"sortable":true},
       {"field":"DossierTyp","label":"Dossier type","type":"string","filterable":true,"sortable":true},
       {"field":"Dokumenttyp","label":"Document type","type":"string","filterable":true,"sortable":true},
       {"field":"DokumenttypNr","label":"Document type no.","type":"string","filterable":true,"sortable":true},
       {"field":"SendungsNr","label":"Consignment no.","type":"string","filterable":true,"sortable":true}]',
    1, 360);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('privera_nachsendungen_total', 'privera_nachsendungen',
        N'Forwardings total', N'Nachsendungen gesamt', N'Réexpéditions au total', N'Inoltri in totale',
        'count', NULL, NULL,
        N'Every forwarding exported in the period, the workbook''s Gesamtergebnis. Group by Forwarding type and Branch for its breakdown.', 'int', 360),
    ('privera_nachsendungen_ohne_tec', 'privera_nachsendungen',
        N'Forwardings without TEC', N'Nachsendungen ohne TEC', N'Réexpéditions sans TEC', N'Inoltri senza TEC',
        'count', NULL, N'[{"field":"Nachsendungstyp","op":"ne","value":"Rechnungen Privera TEC"}]',
        N'The workbook''s hand-added "ohne TEC" line: everything except the "Rechnungen Privera TEC" forwarding type. Not the TEC branch -- excluding that gives a different number.', 'int', 361)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
