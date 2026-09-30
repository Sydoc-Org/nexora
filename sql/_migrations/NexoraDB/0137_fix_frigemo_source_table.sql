-- 0137_fix_frigemo_source_table.sql  (#402)
-- 0127 registered the Frigemo source over SYDOC_Statistik.dbo.Frigemo with
-- columns Date / ImportOverallDocs / ... That table only ever existed on INT
-- (hand-created 2026-09-01 with synthetic rows). The collector on PROD writes
-- dbo.Frigemo_Statistic, whose columns carry the vendor's names, so every run
-- of the source on PROD died with "Invalid object name 'dbo.Frigemo'".
--
-- Repoint the source at the real table and rename the catalog fields to the
-- real columns. Labels, metric codes and permissions are unchanged, and no
-- saved report referenced the old field names on PROD (checked 2026-09-29).
-- DCD is a varchar(512) holding an ISO date ('2025-02-28'); typed 'date' here
-- so the day/week/month grains CAST it and the date pickers bind date params,
-- which SQL Server converts the column to (date outranks varchar).
-- ExportID is the collector's run id and stays out of the catalog.
--
-- INT's SYDOC_Statistik is a vendor DB outside the migration runner; a matching
-- dbo.Frigemo_Statistic was created there by hand from the synthetic rows so
-- INT rehearses the same SQL. The old INT-only dbo.Frigemo can be dropped.
-- Idempotent: plain UPDATEs keyed on the codes 0127 inserted.

UPDATE dbo.ReportingSources
SET BaseObject = 'dbo.Frigemo_Statistic',
    ColumnsJSON = N'[{"field":"DCD","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"OVERALL_IMP_DOCS","label":"Imported documents","type":"number","filterable":true,"sortable":true},
       {"field":"OVERALL_EXP_DOCS","label":"Exported documents","type":"number","filterable":true,"sortable":true},
       {"field":"OVERALL_IMP_PAGES","label":"Imported pages","type":"number","filterable":true,"sortable":true},
       {"field":"OVERALL_EXP_PAGES","label":"Exported pages","type":"number","filterable":true,"sortable":true},
       {"field":"OVERALL_IMP_INVCRE","label":"Imported invoices","type":"number","filterable":true,"sortable":true},
       {"field":"OVERALL_DEL_DUNNING","label":"Deleted","type":"number","filterable":true,"sortable":true},
       {"field":"T_IMP_NOREP_MAILS","label":"No-reply mails","type":"number","filterable":true,"sortable":true},
       {"field":"T_IMP_NOREP_DOCS","label":"No-reply documents","type":"number","filterable":true,"sortable":true},
       {"field":"T_IMP_NOREP_PAGES","label":"No-reply pages","type":"number","filterable":true,"sortable":true}]',
    UpdatedAt = SYSUTCDATETIME()
WHERE Code = 'frigemo';
GO

UPDATE m
SET m.BaseField = v.BaseField,
    m.UpdatedAt = SYSUTCDATETIME()
FROM dbo.ReportingMetrics m
JOIN (VALUES
    ('frigemo_imported_docs',  'OVERALL_IMP_DOCS'),
    ('frigemo_exported_docs',  'OVERALL_EXP_DOCS'),
    ('frigemo_imported_pages', 'OVERALL_IMP_PAGES'),
    ('frigemo_exported_pages', 'OVERALL_EXP_PAGES'),
    ('frigemo_deleted',        'OVERALL_DEL_DUNNING'),
    ('frigemo_invoices',       'OVERALL_IMP_INVCRE')
) AS v(Code, BaseField) ON v.Code = m.Code
WHERE m.SourceId = 'frigemo';
GO
