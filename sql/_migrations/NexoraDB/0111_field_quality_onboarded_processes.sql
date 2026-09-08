-- 0101_field_quality_onboarded_processes.sql
-- Issue #254, follow-up to 0100. Two changes, both about what the wizard
-- offers rather than how anything is calculated.
--
-- 1) ONBOARDED PROCESSES ONLY. The process picker was listing Octo's raw
--    PROCESS values straight off the telemetry tables, including ones nexora
--    has never onboarded -- BuchererFields, PriveraPostFields, 01_Garantiekarten,
--    01_Invoice_1. Those are not processes anyone reports on anywhere else in
--    the app, and a picker offering them invites reports nobody can act on.
--
--    The view now keeps only rows whose process is registered in
--    dbo.ProcessSources, matched on BOTH the organization and the process name.
--    Matching on the process name alone would be wrong: '02_Invoice' belongs to
--    elektromaterial AND to privera, so onboarding one would silently admit the
--    other. That is why each stream carries its Organizations.organizationcode.
--
--    This is data-driven on purpose, exactly like MappedInNexoraPct's use of
--    FieldAliases: to bring a process back, add a dbo.ProcessSources row --
--    do not edit this view.
--
--    Effect on INT: 58,628 of 69,576 rows survive.
--      dropped  Bucherer / BuchererFields         460 rows  (whole customer)
--      dropped  Geberit  / 01_Garantiekarten      400 rows  (whole customer)
--      dropped  ElektroMaterial / 01_Invoice_1 10,016 rows  (legacy process)
--      dropped  Privera  / PriveraPostFields       72 rows
--    Bucherer and Geberit have no dbo.Organizations row at all, so they carry
--    no organization code and cannot match -- they leave the source entirely
--    until they are onboarded properly.
--
-- 2) The two count measures come off the wizard. 'Field instances' and
--    'Workitems (distinct)' answer "how much data is in scope", not "how well
--    does extraction work", which is what this source is for. Disabled rather
--    than deleted -- dbo.ReportingMetrics is read WHERE Enabled = 1, so this is
--    reversible with a single UPDATE and keeps the definitions on record.
--
-- Idempotent.

GO
-- Schema-adaptive (edited after applied on INT, checksum re-blessed): same
-- PROD-missing-Bucherer-table failure as 0110, same fix -- see its header
-- comment. Dynamic SQL only unions branches whose backing table exists.
DECLARE @cfa TABLE (ord INT IDENTITY, txt NVARCHAR(MAX));
DECLARE @dates TABLE (ord INT IDENTITY, txt NVARCHAR(MAX));

IF OBJECT_ID('[$(StatisticsDb)].dbo.Bucherer_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Bucherer'' AS Customer, N''bucherer'' AS Stream, NULL AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Bucherer_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Compass_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Compass'' AS Customer, N''compass'' AS Stream, N''CMPS'' AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Compass_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Em_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''ElektroMaterial'' AS Customer, N''em'' AS Stream, N''LKTR'' AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Em_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.Geberit_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Geberit'' AS Customer, N''geberit'' AS Stream, NULL AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.Geberit_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraInvoice_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverainvoice'' AS Stream, N''PRVR'' AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraInvoice_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraInvoice2025_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverainvoice2025'' AS Stream, N''PRVR'' AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraInvoice2025_Collect_Field_Attributes');

IF OBJECT_ID('[$(StatisticsDb)].dbo.PriveraPost_Collect_Field_Attributes') IS NOT NULL
INSERT INTO @cfa (txt) VALUES (N'SELECT N''Privera'' AS Customer, N''priverapost'' AS Stream, N''PRVR'' AS OrgCode, WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION FROM [$(StatisticsDb)].dbo.PriveraPost_Collect_Field_Attributes');

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
LEFT JOIN dbo.FieldLabels  fl ON fl.FieldKey = LOWER(fa.TargetKey)
WHERE EXISTS (
        SELECT 1
        FROM dbo.ProcessSources ps
        WHERE ps.ClientCode        = ''default''
          AND ps.OrganizationCode  = cfa.OrgCode
          AND SUBSTRING(ps.ProcessName, CHARINDEX(''.'', ps.ProcessName) + 1, 200)
              = cfa.PROCESS COLLATE DATABASE_DEFAULT
      );';

EXEC sp_executesql @sql;
GO

-- 2) The two count measures leave the wizard.
UPDATE dbo.ReportingMetrics
SET Enabled = 0
WHERE Code IN ('fq_instances', 'fq_workitems');
GO

-- Keep the catalog exactly as 0100 left it -- re-asserted so a partially
-- applied history cannot leave the columns and the view out of step.
UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"FieldKey","label":"Field","type":"string","filterable":true,"sortable":true},
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
WHERE Code = 'field_quality';
GO
