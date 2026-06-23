-- 0031_fix_ms02_statconfig_dossierstatistik.sql
-- Fix the MS02 dashboard-stats source. Migration 0025 seeded the MS02 Statconfig
-- row pointing at 'public.batchtracking' (cols 'datuminexport'/'datumimportiert')
-- -- a table that does NOT exist in the MS02 stats DB (Praesidialdepartement_BS).
-- Every MS02 dashboard query therefore raised UndefinedTable, was swallowed, and
-- MS02 contributed 0 to every KPI. The real per-process stats table is the same
-- columnar table doc-field search uses: public."DossierStatistik", with
-- PascalCase date columns DatumInTempExport (export/processed) and ImportDate.
--
-- INT was already corrected in place; this records the fix so STAGING/PROD get
-- it on deploy. Data only (no DDL). Idempotent: only rewrites the row while it
-- still carries the dead 'batchtracking' table, so re-applying is a clean no-op.
-- The dashboard now reads TableName/ExportColumn/ImportColumn from this row
-- instead of hardcoding them, so keeping the row correct is what matters.

IF EXISTS (
    SELECT 1 FROM dbo.Statconfig
    WHERE ClientCode = 'ms02' AND TableName = 'public.batchtracking'
)
BEGIN
    UPDATE dbo.Statconfig
    SET TableName    = 'public."DossierStatistik"',
        ExportColumn = 'DatumInTempExport',
        ImportColumn = 'ImportDate'
    WHERE ClientCode = 'ms02' AND TableName = 'public.batchtracking';
END
GO
