USE [nexora]
GO
DROP VIEW [dbo].[vEmFieldExtractionQuality]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER OFF
GO
CREATE   VIEW [dbo].[vEmFieldExtractionQuality] AS
SELECT
    cfa.PROCESS                                       AS Process,
    cfa.WORKITEM_ID                                   AS Workitem,
    cfa.FIELD                                         AS Field,
    LOWER(fa.TargetKey)                               AS FieldKey,
    COALESCE(fl.EnglishLabel, cfa.FIELD COLLATE DATABASE_DEFAULT)
                                                      AS FieldLabel,
    cfa.[TYPE]                                        AS FieldType,
    inv.ImportDate                                    AS ImportDate,
    inv.ExportDate                                    AS ExportDate,
    -- Octo stores confidences as 0..1 strings; x100 makes them percentages.
    TRY_CONVERT(float, cfa.CONF_BEST_CANDIDATE) * 100 AS Confidence,
    TRY_CONVERT(float, cfa.CONF_2ND_CANDIDATE)  * 100 AS Confidence2nd,
    TRY_CONVERT(float, cfa.[TIME])                    AS ExtractionTimeMs,
    -- The rate columns are 0/100 FLOATS, not 0/1 ints. The reporting layer
    -- emits a bare AVG(col) (nx_lib/reporting/semantic.py _AGG_SQL) and T-SQL
    -- integer-divides AVG over an int column -- every rate would come back 0
    -- or 1. As 0/100 floats, AVG() *is* the percentage, with no post-maths.
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '' THEN 100e0 ELSE 0e0 END
                                                      AS ExtractedPct,
    -- "Correct" follows the house definition already used by the hand-built
    -- v_EMFieldStatistic view: the machine proposed something AND the validator
    -- left it alone. An empty field the validator also left empty is 'Equal'
    -- but is not a correct extraction.
    CASE WHEN cfa.VALUE_BEFORE_VALIDATION <> '' AND cfa.RESULT = 'Equal'
         THEN 100e0 ELSE 0e0 END                      AS CorrectPct,
    CASE WHEN cfa.RESULT = 'Different' THEN 100e0 ELSE 0e0 END
                                                      AS DeviationPct,
    TRY_CONVERT(float, cfa.IS_SET_BY_MACHINE)         * 100 AS SetByMachinePct,
    TRY_CONVERT(float, cfa.IS_USER_VERIFIED)          * 100 AS UserVerifiedPct,
    TRY_CONVERT(float, cfa.IS_USER_ENTERED)           * 100 AS UserEnteredPct,
    TRY_CONVERT(float, cfa.IS_USER_MODIFIED)          * 100 AS UserModifiedPct,
    TRY_CONVERT(float, cfa.VALUE_FROM_CANDIDATE_LIST) * 100 AS FromCandidateListPct,
    -- Octo emits ~630 distinct "fields" for EM, most of them internal bookkeeping
    -- (DocFilename, ImportDatetime, Val_State). Filtering on this to 100 narrows a
    -- report to the fields nexora actually knows about -- a data-driven allow-list,
    -- where the old v_*FieldStatistic views hardcoded ~20 field names in the WHERE
    -- clause. Widen it by adding dbo.FieldAliases rows, not by editing this view.
    CASE WHEN fa.TargetKey IS NULL THEN 0e0 ELSE 100e0 END
                                                      AS MappedInNexoraPct,
    cfa.VALUE_ORIGIN                                  AS ValueOrigin,
    cfa.HISTORY_SOURCE                                AS HistorySource,
    cfa.STATUS_BEFORE_VALIDATION                      AS StatusBeforeValidation,
    cfa.STATUS_AFTER_VALIDATION                       AS StatusAfterValidation
FROM [SYDOC_Statistik].dbo.Em_Collect_Field_Attributes cfa
-- LEFT, not INNER: the telemetry table is the subject. A row whose workitem has
-- no invoice row (~4% on INT) keeps its quality numbers and simply carries no
-- date, so it drops out of over-time breakdowns instead of out of the source.
LEFT JOIN (
        -- Collapsed to one row per workitem first: EM_Invoice has a few
        -- duplicated WorkItem values (3 of 6786 on INT) and joining it raw
        -- would double those rows, quietly inflating every average.
        SELECT WorkItem,
               MIN(ImportDatetime) AS ImportDate,
               MAX(ExportEM_dt)    AS ExportDate
        FROM [SYDOC_Statistik].dbo.EM_Invoice
        GROUP BY WorkItem
    ) inv ON inv.WorkItem = cfa.WORKITEM_ID
-- Octo field name -> nexora canonical key -> nexora label. Both joins are
-- LEFT: an unmapped field still reports, labelled with its raw Octo name.
-- COLLATE DATABASE_DEFAULT because the two databases disagree on collation
-- (NexoraDB is Latin1_General_CI_AS, the statistics DB SQL_Latin1_General_CP1_CI_AS)
-- and an uncollated cross-database string compare is a hard error, not a warning.
LEFT JOIN dbo.FieldAliases fa
       ON fa.SourceFieldName = cfa.FIELD COLLATE DATABASE_DEFAULT
LEFT JOIN dbo.FieldLabels  fl ON fl.FieldKey        = LOWER(fa.TargetKey);
GO
