-- 0013_category_terms.sql
-- Issue #220, phase 5.1: retire dbo.CategoryTranslations, the last place in
-- this database that stores *table names as data*.
--
-- WHAT THE PLAN ASSUMED, AND WHAT IS ACTUALLY THERE.
-- The plan (D10) said to fold the translations into EffortCategories /
-- QualityCheckCategories as NameDe/NameFr/NameIt columns, on the assumption
-- that those are (Id, Name) catalogues. They are not. Measured on INT
-- 2026-09-10:
--
--   EffortCategories       32 rows  (Id, ParentCategory, SubCategory)
--   QualityCheckCategories 27 rows  (Id, ParentCategory, ParentSubCategory,
--                                    SubCategory)
--
-- They are *combination* tables: 32 effort rows carry only 6 distinct parent
-- categories, and QualityCheckCategories repeats 'GAV Retouren' ten times.
-- CategoryTranslations does not translate rows, it translates the distinct
-- German *terms* appearing in any of those columns -- 6 parents + 30 subs on
-- the effort side, 5 + 3 + 9 on the quality-check side. Adding per-locale
-- columns to the catalogue tables would therefore mean six new columns on one
-- and nine on the other, with every parent's translation duplicated across up
-- to ten rows: a denormalisation with a permanent update anomaly, to remove a
-- join over 162 rows. Not done.
--
-- WHAT THIS DOES INSTEAD. Pivot the table so a term is one row and the locale
-- is a column, which removes both offending columns:
--
--   SourceTable  -- 'EffortCategories' / 'QualityCheckCategories' as data.
--                   Verified disjoint: zero German terms appear under both
--                   source tables, so the partition carries no information.
--                   A shared term dictionary is also more correct -- the same
--                   German word should not get two different French words.
--   Locale       -- one row per (term, locale) becomes one row per term.
--
--   162 rows (53 terms x 3 locales) -> 53 rows.
--
-- Every term has all three of en/fr/it today (verified: no term has a
-- different count), so the pivot loses nothing and NULL means "not translated"
-- rather than "row missing".
--
-- D8 -- deploy.yml applies migrations before it stops the app pool, so old
-- code meets this schema for a few seconds. dbo.CategoryTranslations comes
-- back as a view with the original five columns, deriving SourceTable from the
-- catalogue tables. That view is scaffolding: drop it one release after this
-- ships, together with the phase 5.1 code change. It is NOT dropped by 0014,
-- which only removes the phase 2-3 scaffolding.
--
-- Idempotent.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

IF OBJECT_ID(N'dbo.CategoryTerms', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.CategoryTerms (
        Id     int IDENTITY(1,1) NOT NULL,
        NameDe nvarchar(255)     NOT NULL,
        NameEn nvarchar(255)     NULL,
        NameFr nvarchar(255)     NULL,
        NameIt nvarchar(255)     NULL,
        CONSTRAINT PK_CategoryTerms PRIMARY KEY CLUSTERED (Id),
        CONSTRAINT UQ_CategoryTerms_NameDe UNIQUE (NameDe)
    );
END
GO

-- Populate only from a real table; on a re-run CategoryTranslations is already
-- the view below and the INSERT would be a no-op against its own source.
IF OBJECT_ID(N'dbo.CategoryTranslations', N'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.CategoryTerms)
BEGIN
    INSERT INTO dbo.CategoryTerms (NameDe, NameEn, NameFr, NameIt)
    SELECT  OriginalValue,
            MAX(CASE WHEN Locale = 'en' THEN TranslatedValue END),
            MAX(CASE WHEN Locale = 'fr' THEN TranslatedValue END),
            MAX(CASE WHEN Locale = 'it' THEN TranslatedValue END)
    FROM    dbo.CategoryTranslations
    WHERE   OriginalValue IS NOT NULL
    GROUP BY OriginalValue;

    -- Refuse to drop the source unless every term came across.
    DECLARE @terms int = (SELECT COUNT(DISTINCT OriginalValue)
                          FROM dbo.CategoryTranslations WHERE OriginalValue IS NOT NULL);
    DECLARE @moved int = (SELECT COUNT(*) FROM dbo.CategoryTerms);
    IF @terms <> @moved
        THROW 50013, 'CategoryTerms row count does not match the distinct terms in CategoryTranslations; nothing dropped.', 1;

    -- And unless every translation is reachable under its own locale.
    IF EXISTS (
        SELECT 1
        FROM dbo.CategoryTranslations s
        JOIN dbo.CategoryTerms t ON t.NameDe = s.OriginalValue
        WHERE s.TranslatedValue IS NOT NULL
          AND s.TranslatedValue <> CASE s.Locale
                                       WHEN 'en' THEN t.NameEn
                                       WHEN 'fr' THEN t.NameFr
                                       WHEN 'it' THEN t.NameIt
                                   END
    )
        THROW 50013, 'A CategoryTranslations row did not survive the pivot intact; nothing dropped.', 1;

    DROP TABLE dbo.CategoryTranslations;
END
GO

-- Compat view (D8). dbo.CategoryTranslation -- the singular phase-2 view --
-- selects from this one, so it keeps resolving until 0014 removes it.
IF OBJECT_ID(N'dbo.CategoryTranslations', N'V') IS NOT NULL
    DROP VIEW dbo.CategoryTranslations;
GO
CREATE VIEW dbo.CategoryTranslations
AS
SELECT  t.Id * 10 + l.Ord AS ID,
        st.SourceTable,
        t.NameDe          AS OriginalValue,
        l.Locale,
        CASE l.Locale WHEN 'en' THEN t.NameEn
                      WHEN 'fr' THEN t.NameFr
                      ELSE           t.NameIt END AS TranslatedValue
FROM        dbo.CategoryTerms t
CROSS JOIN  (VALUES (1, 'en'), (2, 'fr'), (3, 'it')) AS l (Ord, Locale)
CROSS APPLY (
    SELECT CASE WHEN EXISTS (
                     SELECT 1 FROM dbo.QualityCheckCategories q
                     WHERE t.NameDe IN (q.ParentCategory, q.ParentSubCategory, q.SubCategory))
                THEN 'QualityCheckCategories'
                ELSE 'EffortCategories'
           END AS SourceTable
) st;
GO
