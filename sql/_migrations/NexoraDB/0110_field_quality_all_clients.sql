-- 0100_field_quality_all_clients.sql
-- Issue #254, follow-up to 0097-0099. EM was the pilot; this rolls the source
-- out to all seven of the statistics DB's *_Collect_Field_Attributes tables.
--
-- Shape: ONE source with a Customer dimension, not seven near-identical ones.
-- All seven tables are column-identical (verified on INT), and dbo.FieldAliases
-- is a flat global map, so "Rechnungsnummer" at one customer and "InvoiceNo" at
-- another both land on the canonical key 'invoicenr'. Unioning is therefore the
-- whole point: it is what lets you rank the SAME field across customers. Seven
-- separate sources could not answer that, and would have meant 63 duplicated
-- measure rows to keep in step.
--
--   stream              customer          telemetry table (rows on INT)
--   bucherer            Bucherer          Bucherer_Collect_Field_Attributes (460)
--   compass             Compass           Compass_Collect_Field_Attributes (15,872)
--   em                  ElektroMaterial   Em_Collect_Field_Attributes (17,107)
--   geberit             Geberit           Geberit_Collect_Field_Attributes (400)
--   priverainvoice      Privera           PriveraInvoice_Collect_Field_Attributes (1,479)
--   priverainvoice2025  Privera           PriveraInvoice2025_Collect_Field_Attributes (29,756)
--   priverapost         Privera           PriveraPost_Collect_Field_Attributes (4,502)
--
-- Customer names match dbo.Organizations.Organization where a row exists
-- (Compass, ElektroMaterial, Privera); Bucherer and Geberit have none, so their
-- names are literals here. They are literals for all seven on purpose: joining
-- Organizations would couple this view to the tenancy tables being reshaped in
-- #255, to earn two labels.
--
-- Stream exists because Privera has THREE telemetry tables across TWO header
-- tables. Keying the date join on Customer would let a workitem id present in
-- both PriveraInvoice and PriveraPosteingang match twice and silently double
-- those rows, inflating every average. Keyed on Stream the join is 1:1 by
-- construction.
--
-- Date sources come from dbo.ProcessSources where it documents the process
-- (Compass, EM, PriveraPost, PriveraInvoice). Bucherer and Geberit are not in
-- ProcessSources; their header tables have Compass's column shape, so they use
-- the same ImportDate/UploadDatetime pair. Every join is LEFT -- a stream whose
-- header table does not line up (Bucherer matches 0 of its 2 workitems on INT)
-- still reports its quality numbers, just carrying no date.
--
-- Also renames the source em_field_quality -> field_quality now that it is not
-- EM-only. Safe: the source has never been deployed -- it exists on INT only,
-- from 0097 on this branch -- and no saved report references it. The Reports
-- rewrite below is belt-and-braces for a report saved on a dev box in between.
--
-- Idempotent.
--
-- Schema-adaptive (edited after applied on INT, checksum re-blessed): PROD's
-- SYDOC_Statistik is missing Bucherer_Collect_Field_Attributes -- Bucherer's
-- collector pipeline is INT-only, not yet a live PROD client. A plain CREATE
-- VIEW referencing it fails at CREATE time (cross-database three-part names
-- are bound eagerly, unlike same-database deferred name resolution), taking
-- the whole migration batch down with it -- exactly the "fails on a fresh
-- database, nothing added later can rescue it" case docs/howto/db-migrations.md
-- documents fixing in place. The view is now built as dynamic SQL that only
-- unions branches whose backing table actually exists on the target server,
-- so a customer missing from one environment degrades to "not in the view"
-- rather than blocking every migration after it.

-- 1) The unified view. One row per (stream, workitem, field) -- the same grain
--    as the underlying tables. The extraction-quality maths is written ONCE
--    here rather than seven times; see 0097 for why each expression looks like
--    it does (0/100 floats, the RESULT flag, the LEFT joins).
GO
DECLARE @cfa TABLE (ord INT IDENTITY, txt NVARCHAR(MAX));
DECLARE @dates TABLE (ord INT IDENTITY, txt NVARCHAR(MAX));

IF OBJECT_ID('[$(StatisticsDb)].dbo.Bucherer_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Bucherer'' AS Customer, N''bucherer'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Bucherer_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Compass_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Compass'' AS Customer, N''compass'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Compass_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Em_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''ElektroMaterial'' AS Customer, N''em'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Em_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Geberit_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Geberit'' AS Customer, N''geberit'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Geberit_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraInvoice_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverainvoice'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraInvoice_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraInvoice2025_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverainvoice2025'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraInvoice2025_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraPost_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverapost'' AS Stream, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraPost_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Bucherer_Invoice') IS NOT NULL
INSERT INTO @dates (txt) VALUES (N'SELECT N''bucherer'' AS Stream, CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate FROM [$(StatisticsDb)].dbo.Bucherer_Invoice GROUP BY CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Compass_Invoice') IS NOT NULL
INSERT INTO @dates (txt) VALUES (N'SELECT N''compass'' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate FROM [$(StatisticsDb)].dbo.Compass_Invoice GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT');

IF OBJECT_ID('[$(StatisticsDb)].dbo.EM_Invoice') IS NOT NULL
INSERT INTO @dates (txt) VALUES (N'SELECT N''em'' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportDatetime]) AS ImportDate, MAX([ExportEM_dt]) AS ExportDate FROM [$(StatisticsDb)].dbo.EM_Invoice GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Geberit_Garantiekarten') IS NOT NULL
INSERT INTO @dates (txt) VALUES (N'SELECT N''geberit'' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate FROM [$(StatisticsDb)].dbo.Geberit_Garantiekarten GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraInvoice') IS NOT NULL
BEGIN
INSERT INTO @dates (txt) VALUES (N'SELECT N''priverainvoice'' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate FROM [$(StatisticsDb)].dbo.PriveraInvoice GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT');
INSERT INTO @dates (txt) VALUES (N'SELECT N''priverainvoice2025'' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate FROM [$(StatisticsDb)].dbo.PriveraInvoice GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT');
END

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraPosteingang') IS NOT NULL
INSERT INTO @dates (txt) VALUES (N'SELECT N''priverapost'' AS Stream, CONVERT(nvarchar(50), [WorkItemID]) COLLATE DATABASE_DEFAULT AS Workitem, MIN([ImportDatetime_dt]) AS ImportDate, MAX([ExportDatetime_dt]) AS ExportDate FROM [$(StatisticsDb)].dbo.PriveraPosteingang GROUP BY CONVERT(nvarchar(50), [WorkItemID]) COLLATE DATABASE_DEFAULT');

DECLARE @cfaSql NVARCHAR(MAX) = (SELECT STRING_AGG(txt, N' UNION ALL ') WITHIN GROUP (ORDER BY ord) FROM @cfa);
DECLARE @datesSql NVARCHAR(MAX) = (SELECT STRING_AGG(txt, N' UNION ALL ') WITHIN GROUP (ORDER BY ord) FROM @dates);

DECLARE @sql NVARCHAR(MAX) = N'
CREATE OR ALTER VIEW dbo.vFieldExtractionQuality AS
WITH cfa AS (' + @cfaSql + N'),
dates AS (' + @datesSql + N')
SELECT
    cfa.Customer                                      AS Customer,
    cfa.Stream                                        AS Stream,
    cfa.PROCESS                                       AS Process,
    cfa.WORKITEM_ID                                   AS Workitem,
    cfa.FIELD                                         AS Field,
    LOWER(fa.TargetKey)                               AS FieldKey,
    COALESCE(fl.EnglishLabel, cfa.FIELD COLLATE DATABASE_DEFAULT)
                                                      AS FieldLabel,
    cfa.[TYPE]                                        AS FieldType,
    d.ImportDate                                      AS ImportDate,
    d.ExportDate                                      AS ExportDate,
    TRY_CONVERT(float, cfa.CONF_BEST_CANDIDATE) * 100 AS Confidence,
    TRY_CONVERT(float, cfa.CONF_2ND_CANDIDATE)  * 100 AS Confidence2nd,
    TRY_CONVERT(float, cfa.[TIME])                    AS ExtractionTimeMs,
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '''' THEN 100e0 ELSE 0e0 END
                                                      AS ExtractedPct,
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '''' AND cfa.[RESULT] = ''Equal''
         THEN 100e0 ELSE 0e0 END                      AS CorrectPct,
    CASE WHEN cfa.[RESULT] = ''Different'' THEN 100e0 ELSE 0e0 END
                                                      AS DeviationPct,
    TRY_CONVERT(float, cfa.IS_SET_BY_MACHINE)         * 100 AS SetByMachinePct,
    TRY_CONVERT(float, cfa.IS_USER_VERIFIED)          * 100 AS UserVerifiedPct,
    TRY_CONVERT(float, cfa.IS_USER_ENTERED)           * 100 AS UserEnteredPct,
    TRY_CONVERT(float, cfa.IS_USER_MODIFIED)          * 100 AS UserModifiedPct,
    TRY_CONVERT(float, cfa.VALUE_FROM_CANDIDATE_LIST) * 100 AS FromCandidateListPct,
    CASE WHEN fa.TargetKey IS NULL THEN 0e0 ELSE 100e0 END
                                                      AS MappedInNexoraPct,
    cfa.VALUE_ORIGIN                                  AS ValueOrigin,
    cfa.HISTORY_SOURCE                                AS HistorySource,
    cfa.STATUS_BEFORE_VALIDATION                      AS StatusBeforeValidation,
    cfa.STATUS_AFTER_VALIDATION                       AS StatusAfterValidation
FROM cfa
LEFT JOIN dates d
       ON d.Stream   = cfa.Stream
      AND d.Workitem = cfa.WORKITEM_ID COLLATE DATABASE_DEFAULT
LEFT JOIN dbo.FieldAliases fa
       ON fa.SourceFieldName = cfa.FIELD COLLATE DATABASE_DEFAULT
LEFT JOIN dbo.FieldLabels  fl ON fl.FieldKey = LOWER(fa.TargetKey);';

EXEC sp_executesql @sql;
GO

-- 2) Repoint the source: new code, new label, new base object, Customer and
--    Stream added to the catalog. Everything else is 0099's catalog verbatim.
UPDATE dbo.ReportingSources
SET Code        = 'field_quality',
    Label       = 'Field extraction quality',
    BaseObject  = 'dbo.vFieldExtractionQuality',
    ColumnsJSON = N'[{"field":"FieldKey","label":"Field","type":"string","filterable":true,"sortable":true},
       {"field":"Customer","label":"Customer","type":"string","filterable":true,"sortable":true},
       {"field":"FieldLabel","label":"Field (incl. unmapped)","type":"string","filterable":true,"sortable":true},
       {"field":"Field","label":"Field (Octo raw name)","type":"string","filterable":true,"sortable":true},
       {"field":"FieldType","label":"Field type","type":"string","filterable":true,"sortable":true},
       {"field":"Process","label":"Process","type":"string","filterable":true,"sortable":true},
       {"field":"Stream","label":"Stream","type":"string","filterable":true,"sortable":true},
       {"field":"Workitem","label":"Workitem","type":"string","filterable":true,"sortable":true},
       {"field":"ImportDate","label":"Import date","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"ExportDate","label":"Export date","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"Confidence","label":"Confidence %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"Confidence2nd","label":"2nd-candidate confidence %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ExtractionTimeMs","label":"Extraction time (ms)","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ExtractedPct","label":"Extracted %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"CorrectPct","label":"Extraction correct %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"DeviationPct","label":"Deviation %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"SetByMachinePct","label":"Set by machine %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserVerifiedPct","label":"User verified %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserEnteredPct","label":"User entered %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserModifiedPct","label":"User corrected %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"FromCandidateListPct","label":"From candidate list %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"MappedInNexoraPct","label":"Mapped in nexora %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ValueOrigin","label":"Value origin","type":"string","filterable":true,"sortable":true},
       {"field":"HistorySource","label":"History source","type":"string","filterable":true,"sortable":true},
       {"field":"StatusBeforeValidation","label":"Status before validation","type":"string","filterable":true,"sortable":true},
       {"field":"StatusAfterValidation","label":"Status after validation","type":"string","filterable":true,"sortable":true}]'
WHERE Code IN ('em_field_quality', 'field_quality');
GO

UPDATE dbo.ReportingMetrics SET SourceId = 'field_quality' WHERE SourceId = 'em_field_quality';
GO

-- 3) A report saved against the old code between 0097 and here would dangle.
--    There are none on INT and the source never reached PROD, but rewriting is
--    one statement and losing someone's saved report to a rename is not on.
UPDATE dbo.Reports
SET DefinitionJSON = REPLACE(DefinitionJSON, 'em_field_quality', 'field_quality')
WHERE DefinitionJSON LIKE '%em_field_quality%';
GO

-- 4) The EM-only view is superseded.
DROP VIEW IF EXISTS dbo.vEmFieldExtractionQuality;
GO
