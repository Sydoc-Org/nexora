-- 0037_reporting_processname_label.sql
-- Localized label for the reporting catalog's synthetic 'processname'
-- dimension (labels are DB-driven i18n via Search_Field_Labels; without a
-- row the catalog falls back to the title-cased key "Processname").
-- The Simple-tab wizard un-hides this dimension in the same release: each
-- Octo process corresponds to an actual client, so "break down by Process"
-- delivers per-client numbers. Deliberately NOT labeled "Client" -- a
-- 'client' doc-field chip already exists in the wizard.
-- Safe for the workitems doc-field UI: no col_processname exists in
-- SearchConfig, so this row can never surface a phantom search filter.

IF NOT EXISTS (SELECT 1 FROM dbo.Search_Field_Labels WHERE FieldKey = 'processname')
    INSERT INTO dbo.Search_Field_Labels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
    VALUES ('processname', 'Process', 'Prozess', 'Processus', 'Processo', 0);
GO
