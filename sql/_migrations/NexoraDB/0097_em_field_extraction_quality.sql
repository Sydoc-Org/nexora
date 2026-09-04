-- 0097_em_field_extraction_quality.sql
-- Issue #254: put Octo's per-field extraction telemetry on the Reporting page.
--
-- The statistics DB holds one *_Collect_Field_Attributes table per client,
-- written by the Octo runtime: one row per (workitem, document field) carrying
-- the value the machine extracted, the value the validator ended up with, and
-- the extractor's confidence in its best and second-best candidate. The data
-- has been accumulating for years and nothing read it.
--
-- This registers the EM (ElektroMaterial) table as a curated reporting source,
-- so a user can rank fields by how well they actually extract. EM is the pilot;
-- the six other tables (Compass, PriveraPost, PriveraInvoice,
-- PriveraInvoice2025, Bucherer, Geberit) take the same shape once it proves out.
--
-- The view lives in NexoraDB -- app-owned, migration-tracked, and next to the
-- FieldAliases / FieldLabels registries it needs to translate Octo's raw field
-- names into nexora's vocabulary. It reaches across to the statistics DB, whose
-- name differs per environment (SYDOC_Statistik / sydoc_stat / sydoc_stat_INT),
-- via the $(StatisticsDb) sqlcmd variable that scripts/db-migrate.py supplies.
--
-- Deliberately NOT exposed: VALUE_BEFORE_VALIDATION / VALUE_AFTER_VALIDATION
-- (raw customer document content), MSG_BEFORE_VALIDATION, DOCUMENT_NAME,
-- DEFNAME, and the validating user. This source answers "which fields extract
-- well", not "what did this invoice say" or "who fixed it".
--
-- Idempotent.

-- 1) The view. One row per (workitem, field) instance, same grain as the
--    underlying table.
GO
CREATE OR ALTER VIEW dbo.vEmFieldExtractionQuality AS
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
FROM [$(StatisticsDb)].dbo.Em_Collect_Field_Attributes cfa
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
        FROM [$(StatisticsDb)].dbo.EM_Invoice
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

-- 2) Permission, seeded onto the same profiles that already hold admin.view
--    (mirrors migration 0011's pattern for the other curated table sources).
INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    ('reporting.source.field_quality',
     'Reporting: use the Field extraction quality source')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.source.field_quality'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- 3) The source. Engine 'statistics' is deliberately NOT used: the view is a
--    NexoraDB object, so it reads on the 'nexora' engine and needs no new
--    credential. BaseObject stays two-part so the engine supplies the database.
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'em_field_quality')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'em_field_quality', 'curated', 'Field extraction quality (EM)',
    'reporting.source.field_quality', 'nexora', 'table', 'dbo.vEmFieldExtractionQuality',
    N'[{"field":"Field","label":"Field (Octo name)","type":"string","filterable":true,"sortable":true},
       {"field":"FieldLabel","label":"Field","type":"string","filterable":true,"sortable":true},
       {"field":"FieldKey","label":"Field key (nexora)","type":"string","filterable":true,"sortable":true},
       {"field":"FieldType","label":"Field type","type":"string","filterable":true,"sortable":true},
       {"field":"Process","label":"Process","type":"string","filterable":true,"sortable":true},
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
       {"field":"StatusAfterValidation","label":"Status after validation","type":"string","filterable":true,"sortable":true}]',
    1, 40);
GO

-- 4) Measures. Every rate is an AVG over a 0/100 column, so the number that
--    comes back is already a percentage.
INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
     Aggregation, BaseField, Description, Format, Enabled, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It,
       v.Agg, v.BaseField, v.Descr, v.Fmt, 1, v.Sort
FROM (VALUES
    ('fq_instances', 'em_field_quality',
     'Field instances', N'Feldinstanzen', N'Occurrences de champ', N'Istanze di campo',
     'count', NULL,
     'Number of extracted field instances in scope (one per field per workitem)',
     'int', 10),
    ('fq_workitems', 'em_field_quality',
     'Workitems (distinct)', N'Workitems (eindeutig)', N'Workitems (distincts)', N'Workitem (distinti)',
     'count_distinct', 'Workitem',
     'Number of distinct workitems contributing to the numbers in scope',
     'int', 20),
    ('fq_correct_rate', 'em_field_quality',
     'Extraction correct %', N'Extraktion korrekt %', N'Extraction correcte %', N'Estrazione corretta %',
     'avg', 'CorrectPct',
     'Share of field instances the machine proposed and the validator left unchanged -- the headline extraction-quality number',
     'int', 30),
    ('fq_extracted_rate', 'em_field_quality',
     'Extracted %', N'Extrahiert %', N'Extrait %', N'Estratto %',
     'avg', 'ExtractedPct',
     'Share of field instances where the machine proposed any value at all (whether or not it was right)',
     'int', 40),
    ('fq_deviation_rate', 'em_field_quality',
     'Deviation %', N'Abweichung %', N'Écart %', N'Scostamento %',
     'avg', 'DeviationPct',
     'Share of field instances where the validated value differs from the extracted one',
     'int', 50),
    ('fq_user_modified_rate', 'em_field_quality',
     'User corrected %', N'Von Benutzer korrigiert %', N'Corrigé par l''utilisateur %', N'Corretto dall''utente %',
     'avg', 'UserModifiedPct',
     'Share of field instances a validator actively changed -- the manual-effort cost of a field',
     'int', 60),
    ('fq_avg_confidence', 'em_field_quality',
     'Avg. confidence %', N'Ø Konfidenz %', N'Confiance moy. %', N'Confidenza media %',
     'avg', 'Confidence',
     'Mean confidence the extractor reported for its best candidate',
     'int', 70),
    ('fq_avg_confidence_2nd', 'em_field_quality',
     'Avg. 2nd-candidate confidence %', N'Ø Konfidenz 2. Kandidat %', N'Confiance moy. 2e candidat %', N'Confidenza media 2° candidato %',
     'avg', 'Confidence2nd',
     'Mean confidence of the runner-up candidate; close to the best candidate means the extractor was torn between two readings',
     'int', 80),
    ('fq_avg_time', 'em_field_quality',
     'Avg. extraction time (ms)', N'Ø Extraktionszeit (ms)', N'Temps d''extraction moy. (ms)', N'Tempo medio di estrazione (ms)',
     'avg', 'ExtractionTimeMs',
     'Mean time the extractor spent on the field, in milliseconds',
     'int', 90)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Descr, Fmt, Sort)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
