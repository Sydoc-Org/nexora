USE [nexora]
GO
DROP VIEW [dbo].[vFieldExtractionQuality]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER OFF
GO
CREATE   VIEW [dbo].[vFieldExtractionQuality] AS
WITH cfa AS (
    SELECT N'Bucherer' AS Customer, N'bucherer' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.Bucherer_Collect_Field_Attributes
    UNION ALL
    SELECT N'Compass' AS Customer, N'compass' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.Compass_Collect_Field_Attributes
    UNION ALL
    SELECT N'ElektroMaterial' AS Customer, N'em' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.Em_Collect_Field_Attributes
    UNION ALL
    SELECT N'Geberit' AS Customer, N'geberit' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.Geberit_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverainvoice' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.PriveraInvoice_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverainvoice2025' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.PriveraInvoice2025_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverapost' AS Stream,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [SYDOC_Statistik].dbo.PriveraPost_Collect_Field_Attributes
),
dates AS (
    SELECT N'bucherer' AS Stream, CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.Bucherer_Invoice
    GROUP BY CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'compass' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.Compass_Invoice
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'em' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDatetime]) AS ImportDate, MAX([ExportEM_dt]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.EM_Invoice
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'geberit' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.Geberit_Garantiekarten
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverainvoice' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.PriveraInvoice
    GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverainvoice2025' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.PriveraInvoice
    GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverapost' AS Stream, CONVERT(nvarchar(50), [WorkItemID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDatetime_dt]) AS ImportDate, MAX([ExportDatetime_dt]) AS ExportDate
    FROM [SYDOC_Statistik].dbo.PriveraPosteingang
    GROUP BY CONVERT(nvarchar(50), [WorkItemID]) COLLATE DATABASE_DEFAULT
)
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
    -- Octo stores confidences as 0..1 strings; x100 makes them percentages.
    TRY_CONVERT(float, cfa.CONF_BEST_CANDIDATE) * 100 AS Confidence,
    TRY_CONVERT(float, cfa.CONF_2ND_CANDIDATE)  * 100 AS Confidence2nd,
    TRY_CONVERT(float, cfa.[TIME])                    AS ExtractionTimeMs,
    -- 0/100 FLOATS, not 0/1 ints: the reporting layer emits a bare AVG(col) and
    -- T-SQL integer-divides AVG over an int column. As floats, AVG() *is* the
    -- percentage, with no post-maths.
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '' THEN 100e0 ELSE 0e0 END
                                                      AS ExtractedPct,
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '' AND cfa.[RESULT] = 'Equal'
         THEN 100e0 ELSE 0e0 END                      AS CorrectPct,
    CASE WHEN cfa.[RESULT] = 'Different' THEN 100e0 ELSE 0e0 END
                                                      AS DeviationPct,
    TRY_CONVERT(float, cfa.IS_SET_BY_MACHINE)         * 100 AS SetByMachinePct,
    TRY_CONVERT(float, cfa.IS_USER_VERIFIED)          * 100 AS UserVerifiedPct,
    TRY_CONVERT(float, cfa.IS_USER_ENTERED)           * 100 AS UserEnteredPct,
    TRY_CONVERT(float, cfa.IS_USER_MODIFIED)          * 100 AS UserModifiedPct,
    TRY_CONVERT(float, cfa.VALUE_FROM_CANDIDATE_LIST) * 100 AS FromCandidateListPct,
    -- Octo emits hundreds of distinct "fields" per stream, most of them internal
    -- bookkeeping. Filtering this to 100 narrows a report to the fields nexora
    -- actually knows about. Widen it by adding dbo.FieldAliases rows, not by
    -- editing this view.
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
-- COLLATE DATABASE_DEFAULT: NexoraDB is Latin1_General_CI_AS, the statistics DB
-- SQL_Latin1_General_CP1_CI_AS, and an uncollated cross-database string compare
-- is a hard error, not a warning.
LEFT JOIN dbo.FieldAliases fa
       ON fa.SourceFieldName = cfa.FIELD COLLATE DATABASE_DEFAULT
LEFT JOIN dbo.FieldLabels  fl ON fl.FieldKey = LOWER(fa.TargetKey);
GO
