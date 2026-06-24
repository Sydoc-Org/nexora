-- Drop 12 unused columns from dbo.SearchConfig: legacy scan-batch, personal-file,
-- target-system, and masterdata fields that are no longer populated or read by the
-- app. All are nvarchar(100) NULL with no default/PK/index dependency, so they drop
-- cleanly.
--
-- Idempotent: one DROP COLUMN IF EXISTS per column. (A shared IF EXISTS over a
-- comma-list only guards the *first* column in SQL Server, so each gets its own
-- statement — this lets the pre-commit hook re-apply the file without erroring.)

ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_scanbatchnr];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_pid];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_personalfileid];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_employmentfileid];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_doctypeidtargetsystem];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_doctypeidsydoc];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_registeridtargetsystem];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_masterdataseparatorsheettype];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_masterdatabirthday];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_masterdatafirstname];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_masterdatalastname];
ALTER TABLE dbo.SearchConfig DROP COLUMN IF EXISTS [col_masterdataseparatorsheetid];
GO
