-- 0024_statconfig_clientcode.sql
-- Tag each Statconfig row with the client whose stats engine serves it.
-- 'default' rows -> StatisticsDB (T-SQL); 'ms02' rows -> the MS02 stats engine
-- (Praesidialdepartement_BS, Postgres). The dashboard groups by ClientCode.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.Statconfig') AND name = 'ClientCode'
)
BEGIN
    ALTER TABLE dbo.Statconfig
        ADD ClientCode NVARCHAR(50) NOT NULL
        CONSTRAINT DF_Statconfig_ClientCode DEFAULT 'default';
END
GO
-- MS02 process rows: gate MS02 dashboard stats by permission. All MS02 rows
-- point at the SAME table (public.batchtracking in the separate
-- Praesidialdepartement_BS DB) with NO per-process filter -- the dashboard
-- dedupes them to ONE query. Seed one row per MS02 ProcessName the dashboard
-- should expose (owner fills the ProcessName list), then uncomment:
-- INSERT INTO dbo.Statconfig (ProcessName, TableName, ExportColumn, ImportColumn, additionalCondition, ClientCode)
-- VALUES ('<ms02client>.<process>', 'public.batchtracking', 'datuminexport', 'datumimportiert', NULL, 'ms02');
-- GO
