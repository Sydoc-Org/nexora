-- Drop the four synonyms hand-added on PROD during the 2026-08-28 half-deploy
-- rescue (#228): they aliased the pre-0075 mapping-table names onto the
-- decapitated_* tables so the stranded old app could keep serving. The deployed
-- app reads the new names only. INT never had them, so this is a no-op there.
DROP SYNONYM IF EXISTS dbo.SearchConfig;
GO
DROP SYNONYM IF EXISTS dbo.StatConfig;
GO
DROP SYNONYM IF EXISTS dbo.IndexFieldMappings;
GO
DROP SYNONYM IF EXISTS dbo.Search_Field_Labels;
GO
