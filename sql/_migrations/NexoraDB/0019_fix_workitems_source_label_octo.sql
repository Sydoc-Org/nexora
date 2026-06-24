-- 0019_fix_workitems_source_label_octo.sql
-- "Octopus" is shortened to "Octo" in user-facing copy. Rename the curated
-- Workitems source's display Label (shown in the Reporting source dropdown) and
-- its permission Description (shown in the admin access-control grant UI).
-- The source Code ('workitems'), the permission Code
-- ('reporting.source.workitems'), and the Engine value ('octopus') are
-- identifiers and stay unchanged. Idempotent (no-op once already renamed).
UPDATE dbo.ReportingSources
SET Label = N'Workitems (Octo)'
WHERE Code = 'workitems'
  AND Label = N'Workitems (Octopus)';
GO

UPDATE dbo.Permission
SET Description = N'Reporting: use the Workitems (Octo) source'
WHERE Code = 'reporting.source.workitems'
  AND Description = N'Reporting: use the Workitems (Octopus) source';
GO
