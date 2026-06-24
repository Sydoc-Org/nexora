-- Backfill dbo.SearchConfig.col_targetsystemfilename for the elektromaterial /
-- privera process rows: sets the source field each process maps its exported
-- target-system filename from.
--
-- Idempotent: UPDATE ... SET = constant is naturally re-runnable, and the whole
-- block is guarded on the column still existing so it no-ops cleanly (rather
-- than erroring) if applied against a schema where the column is absent.

IF COL_LENGTH('dbo.SearchConfig', 'col_targetsystemfilename') IS NOT NULL
BEGIN
	UPDATE dbo.SearchConfig SET col_targetsystemfilename = 'FileName'
		WHERE ProcessName IN ('elektromaterial.02_Invoice', 'privera.03_Invoice_New');
	UPDATE dbo.SearchConfig SET col_targetsystemfilename = 'init_Name'
		WHERE ProcessName = 'privera.02_InitialScan';
	UPDATE dbo.SearchConfig SET col_targetsystemfilename = 'FilenamePDF'
		WHERE ProcessName = 'privera.02_Posteingang';
END
GO
