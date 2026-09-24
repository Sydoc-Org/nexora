-- 0008_documents_case_only_rename.sql
-- Issue #220, phase 3 follow-up: dbo.Documents.SourceCSVFileName ->
-- SourceCsvFileName.
--
-- 0007 skipped it. Its guard is `COL_LENGTH(new) IS NULL`, and COL_LENGTH is
-- case-insensitive under this database's SQL_Latin1_General_CP1_CI_AS
-- collation, so it saw SourceCsvFileName as already present and moved on. That
-- guard is right for the other 60 renames; it just cannot express a case-only
-- one. Every other column in the map changed by more than case.
--
-- Nothing functional depends on this -- T-SQL resolves either spelling -- but
-- sql/GeneraliDB/ is generated from the live catalog, so the wrong casing
-- would sit in the committed DDL for good.
--
-- Idempotent, with a case-SENSITIVE existence check.

IF COL_LENGTH(N'dbo.Documents', N'SourceCsvFileName') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.columns
       WHERE object_id = OBJECT_ID(N'dbo.Documents')
         AND name = N'SourceCsvFileName' COLLATE Latin1_General_CS_AS
   )
    EXEC sp_rename N'dbo.Documents.SourceCSVFileName', N'SourceCsvFileName', 'COLUMN';
GO
