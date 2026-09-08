-- 0125_field_quality_all_processes_of_onboarded_customers.sql
-- The field-quality source (0110/0111) unions all seven *_Collect_Field_Attributes
-- tables but 0111 kept only rows whose (organization, process) pair is in
-- dbo.ProcessSources. That gate dropped telemetry of onboarded customers too:
-- ElektroMaterial / 01_Invoice_1 (10,016 rows on INT) and Privera /
-- PriveraPostFields (72). Gate on the organization only from now on -- an
-- onboarded customer reports on all of its field telemetry. Bucherer and
-- Geberit (no organization) stay out, unchanged. View body otherwise identical
-- to 0111. Idempotent (CREATE OR ALTER).

GO
CREATE OR ALTER VIEW dbo.vFieldExtractionQuality AS
WITH cfa AS (
    SELECT N'Bucherer' AS Customer, N'bucherer' AS Stream, NULL AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.Bucherer_Collect_Field_Attributes
    UNION ALL
    SELECT N'Compass' AS Customer, N'compass' AS Stream, N'CMPS' AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.Compass_Collect_Field_Attributes
    UNION ALL
    SELECT N'ElektroMaterial' AS Customer, N'em' AS Stream, N'LKTR' AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.Em_Collect_Field_Attributes
    UNION ALL
    SELECT N'Geberit' AS Customer, N'geberit' AS Stream, NULL AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.Geberit_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverainvoice' AS Stream, N'PRVR' AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.PriveraInvoice_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverainvoice2025' AS Stream, N'PRVR' AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.PriveraInvoice2025_Collect_Field_Attributes
    UNION ALL
    SELECT N'Privera' AS Customer, N'priverapost' AS Stream, N'PRVR' AS OrgCode,
           WORKITEM_ID, PROCESS, FIELD, [TYPE], VALUE_BEFORE_VALIDATION, [RESULT], [TIME], CONF_BEST_CANDIDATE, CONF_2ND_CANDIDATE, IS_SET_BY_MACHINE, IS_USER_VERIFIED, IS_USER_ENTERED, IS_USER_MODIFIED, VALUE_FROM_CANDIDATE_LIST, VALUE_ORIGIN, HISTORY_SOURCE, STATUS_BEFORE_VALIDATION, STATUS_AFTER_VALIDATION
    FROM [$(StatisticsDb)].dbo.PriveraPost_Collect_Field_Attributes
),
dates AS (
    SELECT N'bucherer' AS Stream, CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.Bucherer_Invoice
    GROUP BY CONVERT(nvarchar(50), [Workitem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'compass' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.Compass_Invoice
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'em' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDatetime]) AS ImportDate, MAX([ExportEM_dt]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.EM_Invoice
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'geberit' AS Stream, CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDate]) AS ImportDate, MAX([UploadDatetime]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.Geberit_Garantiekarten
    GROUP BY CONVERT(nvarchar(50), [WorkItem]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverainvoice' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.PriveraInvoice
    GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverainvoice2025' AS Stream, CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportTime]) AS ImportDate, MAX([ExportDate]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.PriveraInvoice
    GROUP BY CONVERT(nvarchar(50), [WID]) COLLATE DATABASE_DEFAULT
    UNION ALL
    SELECT N'priverapost' AS Stream, CONVERT(nvarchar(50), [WorkItemID]) COLLATE DATABASE_DEFAULT AS Workitem,
           MIN([ImportDatetime_dt]) AS ImportDate, MAX([ExportDatetime_dt]) AS ExportDate
    FROM [$(StatisticsDb)].dbo.PriveraPosteingang
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
-- The date join is keyed on Stream, never Customer: Privera has three telemetry
-- tables across two header tables, so a workitem id present in both would match
-- twice under a Customer key and silently double those rows.
LEFT JOIN dates d
       ON d.Stream   = cfa.Stream
      AND d.Workitem = cfa.WORKITEM_ID COLLATE DATABASE_DEFAULT
-- COLLATE DATABASE_DEFAULT: NexoraDB is Latin1_General_CI_AS, the statistics DB
-- SQL_Latin1_General_CP1_CI_AS, and an uncollated cross-database string compare
-- is a hard error, not a warning.
LEFT JOIN dbo.FieldAliases fa
       ON fa.SourceFieldName = cfa.FIELD COLLATE DATABASE_DEFAULT
LEFT JOIN dbo.FieldLabels  fl ON fl.FieldKey = LOWER(fa.TargetKey)
-- Onboarded customers, every process (0125). 0111 also matched the process
-- name, which hid ElektroMaterial's legacy 01_Invoice_1 and Privera's
-- PriveraPostFields telemetry from customers who are otherwise fully onboarded.
-- The organization gate stays: Bucherer and Geberit carry no OrgCode and remain
-- out until they get an Organizations row.
WHERE EXISTS (
        SELECT 1
        FROM dbo.ProcessSources ps
        WHERE ps.ClientCode       = 'default'
          AND ps.OrganizationCode = cfa.OrgCode
      );
GO
