-- 0041_ignore_pdbs_statistik_deletion_markers.sql
-- The MS02/PDBS runtime parks deleted workitems on two deletion-marker activity
-- instances that were missing from dbo.ActivityInstancesToIgnore, so those
-- (deleted) workitems stayed visible in the workitems list. Companion rows to
-- the two 'sydoc.05_PDBS' markers already present. Idempotent.

IF NOT EXISTS (
    SELECT 1 FROM dbo.ActivityInstancesToIgnore
    WHERE ProcessName = 'sydoc.05_PDBS'
      AND ActivityInstanceName = 'Deletion Marker PDBS Dokument Statistik'
)
    INSERT INTO dbo.ActivityInstancesToIgnore (ProcessName, ActivityInstanceName)
    VALUES ('sydoc.05_PDBS', 'Deletion Marker PDBS Dokument Statistik');
GO

IF NOT EXISTS (
    SELECT 1 FROM dbo.ActivityInstancesToIgnore
    WHERE ProcessName = 'sydoc.05_PDBS'
      AND ActivityInstanceName = 'Deletion Marker PDBS Dossier Statistik'
)
    INSERT INTO dbo.ActivityInstancesToIgnore (ProcessName, ActivityInstanceName)
    VALUES ('sydoc.05_PDBS', 'Deletion Marker PDBS Dossier Statistik');
GO
