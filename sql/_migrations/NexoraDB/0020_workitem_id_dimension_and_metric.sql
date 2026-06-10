-- 0020_workitem_id_dimension_and_metric.sql
-- Reporting: synthetic workitem_id field + distinct-workitem-count metric.
--
-- StatConfig.WorkitemColumn maps, per docprocessing process, the Statistics
-- table column holding the workitem id (names vary: WorkItem / WorkitemID /
-- WID ...). The reporting catalog exposes any mapped process under the one
-- canonical field key `workitem_id`; the query builder CASTs every mapping to
-- nvarchar(100) so the cross-process UNION never mixes types. A process whose
-- WorkitemColumn stays NULL simply does not expose the field.
--
-- The `workitem_count` metric (COUNT(DISTINCT workitem_id)) answers "how many
-- workitems" where doc_count counts rows - multi-row workitems counted once.
-- Idempotent.

IF COL_LENGTH(N'dbo.StatConfig', N'WorkitemColumn') IS NULL
    ALTER TABLE dbo.StatConfig ADD WorkitemColumn nvarchar(100) NULL;
GO

-- Per-process mappings (column names verified against the Statistics tables).
-- Guarded by IS NULL so a later manual correction is never clobbered.
UPDATE dbo.StatConfig SET WorkitemColumn = 'WorkItem'
WHERE ProcessName = 'compass.01_Invoice_SAP' AND WorkitemColumn IS NULL;

UPDATE dbo.StatConfig SET WorkitemColumn = 'WorkItem'
WHERE ProcessName = 'elektromaterial.02_Invoice' AND WorkitemColumn IS NULL;

UPDATE dbo.StatConfig SET WorkitemColumn = 'WorkitemID'
WHERE ProcessName = 'privera.02_InitialScan' AND WorkitemColumn IS NULL;

UPDATE dbo.StatConfig SET WorkitemColumn = 'WorkItemID'
WHERE ProcessName = 'privera.02_Posteingang' AND WorkitemColumn IS NULL;

UPDATE dbo.StatConfig SET WorkitemColumn = 'WID'
WHERE ProcessName = 'privera.03_Invoice_New' AND WorkitemColumn IS NULL;
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, Aggregation, BaseField, Description, Format, SortOrder)
SELECT 'workitem_count', 'docprocessing', 'Workitem count (distinct)',
       'count_distinct', 'workitem_id',
       'Number of distinct workitems in scope (multi-row workitems counted once)',
       'int', 20
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'workitem_count');
GO
