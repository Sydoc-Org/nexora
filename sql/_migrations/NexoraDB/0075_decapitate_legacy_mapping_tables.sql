-- 0075: decapitate the legacy doc-field/process mapping tables (#98).
-- Every Python consumer (Tasks 3-9 of the docfield-config-restructure-perf
-- plan) has been cut over to nx_lib/mapping_config.py, which reads the
-- normalized dbo.ProcessSources / ProcessFieldMappings / FieldLabels /
-- FieldAliases tables introduced by 0074. Nothing live reads SearchConfig,
-- StatConfig, IndexFieldMappings, or Search_Field_Labels any more (repo-wide
-- grep gate re-verified before writing this migration).
--
-- Renames only -- data is preserved, not dropped, matching the 0042
-- decapitation convention: a later cycle drops these once nothing surfaces
-- a regression (like 0072 dropped the batch 0042 renamed).
--
-- Idempotent (survives the pre-commit hook re-applying it): each sp_rename
-- is guarded by OBJECT_ID(old) IS NOT NULL AND OBJECT_ID(new) IS NULL.
-- sp_rename's second argument MUST be the BARE new name (never
-- schema-qualified, e.g. N'decapitated_SearchConfig', not
-- N'dbo.decapitated_SearchConfig').
IF OBJECT_ID(N'dbo.SearchConfig', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_SearchConfig', N'U') IS NULL
    EXEC sp_rename N'dbo.SearchConfig', N'decapitated_SearchConfig';
GO
IF OBJECT_ID(N'dbo.StatConfig', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_StatConfig', N'U') IS NULL
    EXEC sp_rename N'dbo.StatConfig', N'decapitated_StatConfig';
GO
IF OBJECT_ID(N'dbo.IndexFieldMappings', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_IndexFieldMappings', N'U') IS NULL
    EXEC sp_rename N'dbo.IndexFieldMappings', N'decapitated_IndexFieldMappings';
GO
IF OBJECT_ID(N'dbo.Search_Field_Labels', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Search_Field_Labels', N'U') IS NULL
    EXEC sp_rename N'dbo.Search_Field_Labels', N'decapitated_Search_Field_Labels';
GO
