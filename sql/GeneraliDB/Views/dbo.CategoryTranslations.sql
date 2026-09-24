USE [Generali]
GO
DROP VIEW [dbo].[CategoryTranslations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE VIEW [dbo].[CategoryTranslations]
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
