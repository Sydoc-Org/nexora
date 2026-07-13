-- 0032_ignore_pdbs_deletion_marker_activities.sql
-- Ignore the PDBS deletion-marker activity instances so they drop out of stats.
-- Idempotent: skip each row that already exists.

INSERT INTO dbo.ActivityInstancesToIgnore (ProcessName, ActivityInstanceName)
SELECT v.ProcessName, v.ActivityInstanceName
FROM (VALUES
    ('sydoc.05_PDBS', 'Deletion Marker PDBS Parent Batch Deletion'),
    ('sydoc.05_PDBS', 'Deletion Marker PDBS Deckblatt')
) AS v(ProcessName, ActivityInstanceName)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.ActivityInstancesToIgnore a
    WHERE a.ProcessName = v.ProcessName
      AND a.ActivityInstanceName = v.ActivityInstanceName
);
GO
