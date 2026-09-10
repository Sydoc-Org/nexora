USE [Generali]
GO
DROP VIEW [dbo].[CategoryTranslation]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- SourceTable values moved with the tables above, so old code reading this view
-- finds no rows for 'AdditionalServices' / 'PDQMMapping' and falls back to the
-- untranslated German labels for the few seconds of the deploy window.
CREATE   VIEW [dbo].[CategoryTranslation] AS
SELECT ID, SourceTable, OriginalValue, Locale, TranslatedValue
FROM dbo.CategoryTranslations;

GO
