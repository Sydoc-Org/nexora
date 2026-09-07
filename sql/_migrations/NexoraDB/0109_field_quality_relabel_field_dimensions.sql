-- 0099_field_quality_relabel_field_dimensions.sql
-- Follow-up to 0097 (#254). The source exposes three field dimensions and the
-- labels pointed people at the wrong one:
--
--   FieldKey    "Field key (nexora)"  ->  21 values  (the useful one, clunky name)
--   FieldLabel  "Field"               -> 631 values  (the tempting one, useless)
--   Field       "Field (Octo name)"   -> 633 values
--
-- FieldLabel falls back to the raw Octo name for the ~611 unmapped fields, so
-- "Field" behaved identically to the raw column and produced 631 series. With a
-- 12-series chart cap and 230 fields that Octo pins at exactly 100 percent
-- (internal bookkeeping it fills from the batch every time), the cap filled
-- entirely with ties and every line rendered flat at the top -- a chart that
-- answers nothing.
--
-- So: "Field" now names the nexora-mapped key, and the raw variants say what
-- they are. FieldKey also moves to the front of the catalog so it is the first
-- breakdown the wizard offers. Labels and order only -- the field keys are
-- unchanged, so saved reports and schedules keep resolving.
--
-- Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = N'[{"field":"FieldKey","label":"Field","type":"string","filterable":true,"sortable":true},
       {"field":"FieldLabel","label":"Field (incl. unmapped)","type":"string","filterable":true,"sortable":true},
       {"field":"Field","label":"Field (Octo raw name)","type":"string","filterable":true,"sortable":true},
       {"field":"FieldType","label":"Field type","type":"string","filterable":true,"sortable":true},
       {"field":"Process","label":"Process","type":"string","filterable":true,"sortable":true},
       {"field":"Workitem","label":"Workitem","type":"string","filterable":true,"sortable":true},
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
       {"field":"ValueOrigin","label":"Value origin","type":"string","filterable":true,"sortable":true},
       {"field":"HistorySource","label":"History source","type":"string","filterable":true,"sortable":true},
       {"field":"StatusBeforeValidation","label":"Status before validation","type":"string","filterable":true,"sortable":true},
       {"field":"StatusAfterValidation","label":"Status after validation","type":"string","filterable":true,"sortable":true}]'
WHERE Code = 'em_field_quality';
GO
