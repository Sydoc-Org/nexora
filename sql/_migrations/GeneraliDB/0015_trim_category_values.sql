-- 0015_trim_category_values.sql
-- Issue #220, phase 5.1 follow-up: remove a trailing space that 0013 exposed.
--
-- dbo.QualityCheckCategories holds 'aus sonstigen Quellen ' (trailing space)
-- under 'GAV Retouren' and 'aus sonstigen Quellen' (no space) under
-- 'GPV Retouren'. Someone typed the same category twice, once with a stray
-- blank, and nothing ever noticed because SQL Server ignores trailing spaces
-- in comparison: `x = y`, `x <> y`, GROUP BY and DISTINCT all treat the two as
-- one value. (Only DATALENGTH tells them apart -- which is why the obvious
-- `WHERE col <> LTRIM(RTRIM(col))` audit finds nothing.)
--
-- It was harmless while dbo.CategoryTranslations stored one row per
-- (term, locale): the table simply carried both spellings, and the app's
-- `dict(cursor.fetchall())` ended up with a key for each. 0013 pivoted that
-- table to one row per term, and GROUP BY collapsed the two spellings into
-- one -- which is correct (both carry byte-identical translations: 'From
-- other sources' / "D'autres sources" / 'Da altre fonti'), but it leaves the
-- padded spelling with no matching key. The translation dict is looked up in
-- JavaScript by exact string, so the five 'GAV Retouren' subcategories would
-- have silently fallen back to German.
--
-- Fixing the data is the honest repair: the space carries no meaning, it makes
-- two indistinguishable entries in the category dropdown, and it would produce
-- the same class of bug again the next time anything keys off these strings.
--
-- Measured 2026-09-10, all of it the same one term:
--   INT   QualityCheckCategories.ParentSubCategory   5 rows (ids 6-10)
--         QualityCheckEntries.ParentSubCategory      2 rows (ids 5, 8)
--   PROD  QualityCheckCategories.ParentSubCategory   5 rows
--         QualityCheckEntries.ParentSubCategory     95 rows
-- PROD carries the real workload, which is why its entry count is the
-- interesting one: 95 quality-check entries would have lost their French and
-- Italian subcategory label the moment 0013 deduplicated the terms.
-- Verified that trimming creates no duplicate catalogue rows (the unpadded
-- twin lives under a different ParentCategory).
--
-- QualityCheckEntries is included because its rows store the category as text,
-- not as a foreign key -- leaving them padded would orphan them from the
-- catalogue the moment anything starts comparing by DATALENGTH.
--
-- Idempotent: re-running trims nothing because nothing is padded any more.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

UPDATE dbo.QualityCheckCategories
   SET ParentCategory    = LTRIM(RTRIM(ParentCategory))
 WHERE DATALENGTH(ParentCategory) <> DATALENGTH(LTRIM(RTRIM(ParentCategory)));

UPDATE dbo.QualityCheckCategories
   SET ParentSubCategory = LTRIM(RTRIM(ParentSubCategory))
 WHERE DATALENGTH(ParentSubCategory) <> DATALENGTH(LTRIM(RTRIM(ParentSubCategory)));

UPDATE dbo.QualityCheckCategories
   SET SubCategory       = LTRIM(RTRIM(SubCategory))
 WHERE DATALENGTH(SubCategory) <> DATALENGTH(LTRIM(RTRIM(SubCategory)));

UPDATE dbo.QualityCheckEntries
   SET ParentCategory    = LTRIM(RTRIM(ParentCategory))
 WHERE DATALENGTH(ParentCategory) <> DATALENGTH(LTRIM(RTRIM(ParentCategory)));

UPDATE dbo.QualityCheckEntries
   SET ParentSubCategory = LTRIM(RTRIM(ParentSubCategory))
 WHERE DATALENGTH(ParentSubCategory) <> DATALENGTH(LTRIM(RTRIM(ParentSubCategory)));

UPDATE dbo.QualityCheckEntries
   SET SubCategory       = LTRIM(RTRIM(SubCategory))
 WHERE DATALENGTH(SubCategory) <> DATALENGTH(LTRIM(RTRIM(SubCategory)));

UPDATE dbo.EffortCategories
   SET ParentCategory    = LTRIM(RTRIM(ParentCategory))
 WHERE DATALENGTH(ParentCategory) <> DATALENGTH(LTRIM(RTRIM(ParentCategory)));

UPDATE dbo.EffortCategories
   SET SubCategory       = LTRIM(RTRIM(SubCategory))
 WHERE DATALENGTH(SubCategory) <> DATALENGTH(LTRIM(RTRIM(SubCategory)));

UPDATE dbo.CategoryTerms
   SET NameDe = LTRIM(RTRIM(NameDe))
 WHERE DATALENGTH(NameDe) <> DATALENGTH(LTRIM(RTRIM(NameDe)));
GO

-- Every catalogue term must now be reachable from CategoryTerms by exact
-- string, which is how the browser looks it up.
IF EXISTS (
    SELECT 1 FROM (
        SELECT ParentCategory AS Term FROM dbo.QualityCheckCategories
        UNION SELECT ParentSubCategory FROM dbo.QualityCheckCategories
        UNION SELECT SubCategory       FROM dbo.QualityCheckCategories
        UNION SELECT ParentCategory    FROM dbo.EffortCategories
        UNION SELECT SubCategory       FROM dbo.EffortCategories
    ) c
    WHERE c.Term IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM dbo.CategoryTerms t
                      WHERE t.NameDe = c.Term
                        AND DATALENGTH(t.NameDe) = DATALENGTH(c.Term))
      -- Terms nobody ever translated are fine; only a byte-level mismatch
      -- against a term that DOES exist is the bug this migration fixes.
      AND EXISTS (SELECT 1 FROM dbo.CategoryTerms t WHERE t.NameDe = c.Term)
)
    THROW 50015, 'A catalogue term still differs from its CategoryTerms row by trailing whitespace.', 1;
GO
