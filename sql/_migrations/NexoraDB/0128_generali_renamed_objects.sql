-- 0128_generali_renamed_objects.sql
-- Issue #220, phase 2, NexoraDB side. GeneraliDB migration 0005 renamed the
-- tenant tables; the reporting registry stores object and column names as
-- *data*, so it has to move with them.
--
-- Seven Generali reporting sources exist (not the one the plan assumed):
-- generali_pdqm, generali_attendance, generali_baseservices, generali_projects,
-- generali_iss, generali_documents, generali_imports. Six are repointed here;
-- generali_documents still reads dbo.v_ReportJobJoinDefinitions, which phase 3
-- renames to v_Documents.
--
-- ColumnsJSON also carries field names, so the two columns that were renamed in
-- 0005 (IssReports.category, ImportRuns.Min/MaxScannedAt) are patched in the
-- stored JSON too. Straight REPLACE on the JSON text: these field tokens are
-- unique inside their own row's document.
--
-- ReportingAiAudit / ReportingSqlAudit are deliberately left alone -- they are
-- a historical record of what was actually run, not a live reference.
--
-- Idempotent.

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.QualityCheckEntries'
WHERE Code = 'generali_pdqm' AND BaseObject = 'dbo.PDQMReport';

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.AttendanceEntries'
WHERE Code = 'generali_attendance' AND BaseObject = 'dbo.Attendance';

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.BaseServiceEntries'
WHERE Code = 'generali_baseservices' AND BaseObject = 'dbo.BaseServices';

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.ProjectEntries'
WHERE Code = 'generali_projects' AND BaseObject = 'dbo.ProjectManagement';

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.IssReports'
WHERE Code = 'generali_iss' AND BaseObject = 'dbo.ReportingISS';

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.ImportRuns'
WHERE Code = 'generali_imports' AND BaseObject = 'dbo.CSVImportLog';
GO

UPDATE dbo.ReportingSources
SET ColumnsJSON = REPLACE(ColumnsJSON, '"field":"category"', '"field":"Category"')
WHERE Code = 'generali_iss' AND ColumnsJSON LIKE '%"field":"category"%';

UPDATE dbo.ReportingSources
SET ColumnsJSON = REPLACE(REPLACE(ColumnsJSON,
        '"field":"MinScanDatum"', '"field":"MinScannedAt"'),
        '"field":"MaxScanDatum"', '"field":"MaxScannedAt"')
WHERE Code = 'generali_imports'
  AND (ColumnsJSON LIKE '%"field":"MinScanDatum"%' OR ColumnsJSON LIKE '%"field":"MaxScanDatum"%');
GO
