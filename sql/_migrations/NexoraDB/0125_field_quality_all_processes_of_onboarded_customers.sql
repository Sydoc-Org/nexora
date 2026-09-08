-- 0125_field_quality_all_processes_of_onboarded_customers.sql
-- The field-quality source (0110/0111) unions all seven *_Collect_Field_Attributes
-- tables but 0111 kept only rows whose (organization, process) pair is in
-- dbo.ProcessSources. That gate dropped telemetry of onboarded customers too:
-- ElektroMaterial / 01_Invoice_1 (10,016 rows on INT) and Privera /
-- PriveraPostFields (72). Gate on the organization only from now on -- an
-- onboarded customer reports on all of its field telemetry. Bucherer and
-- Geberit (no organization) stay out, unchanged. View body otherwise identical
-- to 0111. Idempotent (CREATE OR ALTER).
--
-- Schema-adaptive (edited after applied on INT, checksum re-blessed): the first
-- PROD deploy failed because SYDOC_Statistik has no Bucherer_Collect_Field_Attributes
-- there -- the same failure 0110/0111 hit (PR #286), same fix: dynamic SQL that
-- only unions branches whose backing table exists. Gate is organization-only,
-- as above; the rest of the body is 0111's.

GO
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
        WHERE ps.ClientCode       = ''default''
          AND ps.OrganizationCode = cfa.OrgCode
      );';

EXEC sp_executesql @sql;
GO
