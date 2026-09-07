-- 0098_field_quality_metric_semantics.sql
-- Follow-up to 0097 (#254). Verifying the view against the hand-built
-- SYDOC_Statistik.dbo.v_EMFieldStatistic showed the arithmetic is right --
-- restricted to the same population the two agree exactly on all 21 fields,
-- for both the correctness rate and the confidence. It also surfaced two
-- semantics the measure descriptions glossed over, and a reader who subtracts
-- one percentage from the other gets a wrong answer:
--
--   * "Deviation %" is NOT 100 minus "Extraction correct %". 1,317 of EM's
--     17,107 rows deviate while nothing was extracted at all -- the machine
--     found no candidate and the validator typed a value in. Those count as a
--     deviation but were never a failed extraction.
--
--   * "Extraction correct %" trusts Octo's own RESULT flag rather than
--     comparing the before/after values itself. On 1.7% of rows the flag and a
--     literal string comparison disagree (150 rows flagged Different while
--     identical, 139 flagged Equal while different) -- most likely formatting
--     normalisation inside Octo. This matches what v_EMFieldStatistic has
--     always reported, which is why the two views agree; it is not a
--     character-by-character comparison.
--
-- Descriptions only -- no schema, no measure maths changes. Idempotent.

UPDATE dbo.ReportingMetrics
SET Description =
    'Share of field instances the machine proposed and the validator left unchanged, per Octo''s own RESULT flag (not a literal text comparison; the two disagree on ~2% of rows). Not the complement of Deviation % -- see that measure.'
WHERE Code = 'fq_correct_rate';
GO

UPDATE dbo.ReportingMetrics
SET Description =
    'Share of field instances where the validated value differs from the extracted one. NOT 100 minus Extraction correct %: a row where the machine extracted nothing and the validator typed a value counts as a deviation but was never a failed extraction (about 8% of EM rows).'
WHERE Code = 'fq_deviation_rate';
GO

UPDATE dbo.ReportingMetrics
SET Description =
    'Share of field instances where the machine proposed any value at all, right or wrong. Extraction correct % divided by this is the machine''s hit rate on the ones it did attempt.'
WHERE Code = 'fq_extracted_rate';
GO
