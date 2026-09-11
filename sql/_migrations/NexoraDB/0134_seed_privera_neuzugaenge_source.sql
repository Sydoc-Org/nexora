-- 0134_seed_privera_neuzugaenge_source.sql
-- Privera Neuzugänge (Initialscanning), from AES Sprint 54 (#329), after
-- 0130-0133. Replaces
-- R:\...\Privera\02_Initialscanning\Statistik\PRIVERA Exportierte Neuzugaenge pro Niederlassung_2024.xlsx
-- with a source over the view that workbook's Power Query already reads.
--
-- READ THIS BEFORE TESTING ON INT
-- The view works on PROD -- 240 rows, current data. On INT it is BROKEN: it
-- binds to SYDOC_Statistik1.dbo.PriveraInitialUndNeuzugaenge, note the stray
-- "1", evidently a restore artefact, and selecting from it fails with
--   Invalid object name 'SYDOC_Statistik1.dbo.PriveraInitialUndNeuzugaenge' (208)
--   Could not use view or function ... because of binding errors (4413)
-- So this source will error on INT and work on PROD until somebody repoints the
-- INT copy of the view. Registering it is still right: the registry rows are
-- just data, the workbook it replaces runs against PROD, and holding the whole
-- source back over a broken *dev* copy would be the wrong trade.
--
-- WHY EVERY MEASURE IS A SUM AND THERE IS NO DATE GRAIN
-- The view is already aggregated: one row per JahrExport / MonatExportNr /
-- Niederlassung carrying three counters. There is no date column to group by --
-- only a year and a month number -- so those two are ordinary numeric
-- dimensions here rather than a grainable date. That is not a limitation worth
-- working around: the data has no finer resolution than a month anyway.
--
-- WHAT THE OLD REPORT IS
-- One pivot: rows Niederlassung, columns MonatExport, page filter JahrExport,
-- three data fields -- Dossiers, Register, Seiten. It carries a fourth,
-- "Summe von JahrExport", which is plainly somebody dropping the year into the
-- values by accident (it totals 32,416 for 2026). Not reproduced.
--
-- Verified against the published 2026 workbook: January 191/751/8052, February
-- 137/528/9496, April 137/538/3676, June 365/1437/10687, July 34/132/485,
-- August 2/8/108 -- every closed month exact. September differs only because
-- the workbook was refreshed on 2026-09-01, when the month was one day old.
--
-- Permission follows reporting.source.<code>.use (0088). Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.privera_neuzugaenge.use', N'Use the Privera Neuzugänge source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.privera_neuzugaenge.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'privera_neuzugaenge')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'privera_neuzugaenge', 'curated', N'Privera — Neuzugänge',
    'reporting.source.privera_neuzugaenge.use', 'statistics', 'table',
    'dbo.v_PriveraNeuzugaenge_StatistikNiederlassung_AnzahlDossiers',
    N'[{"field":"JahrExport","label":"Export year","type":"number","filterable":true,"sortable":true},
       {"field":"MonatExportNr","label":"Export month no.","type":"number","filterable":true,"sortable":true},
       {"field":"MonatExport","label":"Export month","type":"string","filterable":true,"sortable":true},
       {"field":"Niederlassung","label":"Branch","type":"string","filterable":true,"sortable":true},
       {"field":"AnzahlDossiersExport","label":"Dossiers","type":"number","filterable":true,"sortable":true},
       {"field":"AnzahlRegisterExport","label":"Registers","type":"number","filterable":true,"sortable":true},
       {"field":"AnzahlSeitenExport","label":"Pages","type":"number","filterable":true,"sortable":true},
       {"field":"Abfragedatum","label":"Queried at","type":"date","filterable":true,"sortable":true,"grainable":true}]',
    1, 370);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('privera_neuzugaenge_dossiers', 'privera_neuzugaenge',
        N'Dossiers', N'Dossiers', N'Dossiers', N'Dossier',
        'sum', 'AnzahlDossiersExport', NULL,
        N'Dossiers exported in the period. The workbook''s "Dossiers" row. Group by Branch and Export month for its layout.', 'int', 370),
    ('privera_neuzugaenge_register', 'privera_neuzugaenge',
        N'Registers', N'Register', N'Registres', N'Registri',
        'sum', 'AnzahlRegisterExport', NULL,
        N'Registers exported in the period -- the workbook''s "Register" row.', 'int', 371),
    ('privera_neuzugaenge_seiten', 'privera_neuzugaenge',
        N'Pages', N'Seiten', N'Pages', N'Pagine',
        'sum', 'AnzahlSeitenExport', NULL,
        N'Pages exported in the period -- the workbook''s "Seiten" row.', 'int', 372)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
