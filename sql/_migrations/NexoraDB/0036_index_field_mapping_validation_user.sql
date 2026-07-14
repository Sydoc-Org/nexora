-- 0036_index_field_mapping_validation_user.sql
-- Owner action 2 from the docfield-permission-gating plan (0035): map Octo's
-- raw extraction index field 'ValUser' to the TargetKey the app's Octo field
-- pipeline (nx_lib/octo.py get_index_field_mappings / get_extensions_urls_fields)
-- keys the detail panel / CSV export fields dict by. 'ValidationUser' (PascalCase,
-- matching this table's existing convention e.g. CrdName, DocBarcode) normalizes
-- to 'validationuser' via _norm_field_token, matching the sensitive FieldKey seeded
-- in Search_Field_Labels by migration 0035 -- so the sensitivity strip now catches it.

IF NOT EXISTS (SELECT 1 FROM dbo.IndexFieldMappings WHERE SourceFieldName = 'ValUser')
    INSERT INTO dbo.IndexFieldMappings (SourceFieldName, TargetKey)
    VALUES ('ValUser', 'ValidationUser');
GO
