-- 0116_field_quality_wizard_curation.sql
-- #254 follow-up: the Field extraction quality wizard offered every view
-- column as a breakdown. Curate the catalog to what a report actually
-- breaks down by:
--
--   * Stream and Workitem leave the catalog (the view keeps both -- Stream is
--     the date-join key, Workitem the grain -- they are just not reportable).
--   * Customer is labelled "Client", the word the rest of the app uses.
--   * Process carries labelWith=Customer, so the scope step and value pickers
--     read "elektromaterial.02_Invoice" like every other process list.
--   * The raw/diagnostic dimensions move behind the wizard's "Advanced"
--     fold via "advanced":true (nx_lib/reporting/table_query.py passes the
--     flag through; static/js/reporting_simple_wizard.js renders it).
--
-- Field keys are unchanged, so saved reports and schedules keep resolving.
-- Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"FieldKey","label":"Field","type":"string","filterable":true,"sortable":true},
       {"field":"Customer","label":"Client","type":"string","filterable":true,"sortable":true},
       {"field":"Process","label":"Process","type":"string","filterable":true,"sortable":true,"labelWith":"Customer"},
       {"field":"FieldLabel","label":"Field (incl. unmapped)","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"Field","label":"Field (Octo raw name)","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"FieldType","label":"Field type","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"ImportDate","label":"Import date","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"ExportDate","label":"Export date","type":"datetime","filterable":true,"sortable":true,"grainable":true},
       {"field":"Confidence","label":"Confidence %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"Confidence2nd","label":"2nd-candidate confidence %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ExtractionTimeMs","label":"Extraction time (ms)","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ExtractedPct","label":"Extracted %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"CorrectPct","label":"Extraction correct %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"DeviationPct","label":"Deviation %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"SetByMachinePct","label":"Set by machine %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserVerifiedPct","label":"User verified %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserEnteredPct","label":"User entered %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"UserModifiedPct","label":"User corrected %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"FromCandidateListPct","label":"From candidate list %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"MappedInNexoraPct","label":"Mapped in nexora %","type":"number","filterable":true,"sortable":true,"aggregable":true},
       {"field":"ValueOrigin","label":"Value origin","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"HistorySource","label":"History source","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"StatusBeforeValidation","label":"Status before validation","type":"string","filterable":true,"sortable":true,"advanced":true},
       {"field":"StatusAfterValidation","label":"Status after validation","type":"string","filterable":true,"sortable":true,"advanced":true}]'
WHERE Code = 'field_quality';
GO
