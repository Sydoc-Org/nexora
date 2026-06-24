-- 0030_ms02_pdbs_docfield_columnar_config.sql
-- Captures the manual SSMS setup that makes MS02 (sydoc.05_PDBS) doc-field search
-- and the prepared-documents PID import work, so STAGING/PROD reproduce it.
--
-- Correction to 0027: the MS02 doc-field source is NOT an EAV table. It is a wide
-- "statistik" table (public."DossierStatistik") with one COLUMN per field plus a
-- WorkItemID column. So the 'ms02' SearchConfig row is configured exactly like a
-- 'default' row -- TableName / TableAlias / JoinCondition / col_<field> = real
-- column names -- and the resolver runs a columnar query on engine_ms02_docfields_pg
-- (see nx_lib/workitem_sources.py). TimeFilter/SuggestionTimeFilter therefore carry
-- POSTGRES syntax (unaliased, double-quoted column; the resolver queries a single
-- table with no alias/join), NOT the T-SQL DATEADD/GETDATE used by 'default' rows.
--
-- Idempotent: column adds are guarded (0002 dropped several col_<field> slots, so a
-- migrations-only PROD lacks them); the SearchConfig/Statconfig rows are upserted;
-- the IndexFieldMappings/search_field_labels seeds insert only what is missing.

-- (1) Ensure the doc-field column slots the PDBS mapping uses exist.
IF COL_LENGTH('dbo.SearchConfig', 'col_docbarcode') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_docbarcode NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.SearchConfig', 'col_archiveboxno') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_archiveboxno NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.SearchConfig', 'col_batchname') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_batchname NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.SearchConfig', 'col_pid') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_pid NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.SearchConfig', 'col_dossierpositioninbatch') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_dossierpositioninbatch NVARCHAR(100) NULL;
GO
IF COL_LENGTH('dbo.SearchConfig', 'col_pagecount') IS NULL
    ALTER TABLE dbo.SearchConfig ADD col_pagecount NVARCHAR(100) NULL;
GO

-- (2) PDBS doc-field config: route to the MS02 Postgres columnar statistik table.
--     ClientCode='ms02' (matching Statconfig) is the load-bearing line -- without
--     it the row falls through the SQL Server 'default' path and never reaches PG.
IF EXISTS (SELECT 1 FROM dbo.SearchConfig WHERE ProcessName = 'sydoc.05_PDBS')
BEGIN
    UPDATE dbo.SearchConfig
    SET ClientCode = 'ms02',
        TableName = 'public."DossierStatistik"',
        TableAlias = 'd',
        JoinCondition = 'd.WorkItemID = twi.id',
        TimeFilter = '"ImportDate" > now() - interval ''6 months''',
        SuggestionTimeFilter = '"ImportDate" >= now() - interval ''7 days''',
        col_docbarcode = 'DossierBarcode',
        col_archiveboxno = 'BoxNummer',
        col_batchname = 'BatchName',
        col_pid = 'DossierNummer',
        col_dossierpositioninbatch = 'DossierPositionInBatch',
        col_pagecount = 'AnzahlSeitenImDossier'
    WHERE ProcessName = 'sydoc.05_PDBS';
END
ELSE
BEGIN
    INSERT INTO dbo.SearchConfig
        (ProcessName, TableName, TableAlias, JoinCondition, TimeFilter,
         SuggestionTimeFilter, ClientCode, col_docbarcode, col_archiveboxno,
         col_batchname, col_pid, col_dossierpositioninbatch, col_pagecount)
    VALUES
        ('sydoc.05_PDBS', 'public."DossierStatistik"', 'd', 'd.WorkItemID = twi.id',
         '"ImportDate" > now() - interval ''6 months''',
         '"ImportDate" >= now() - interval ''7 days''',
         'ms02', 'DossierBarcode', 'BoxNummer', 'BatchName', 'DossierNummer',
         'DossierPositionInBatch', 'AnzahlSeitenImDossier');
END
GO

-- (3) Dashboard-stats columns for PDBS (DossierStatistik); companion to 0025/0028.
IF EXISTS (SELECT 1 FROM dbo.Statconfig WHERE ProcessName = 'sydoc.05_PDBS')
BEGIN
    UPDATE dbo.Statconfig
    SET TableName = 'public."DossierStatistik"',
        ExportColumn = 'DatumInTempExport',
        ImportColumn = 'ImportDate',
        WorkitemColumn = 'WorkItemID',
        ClientCode = 'ms02'
    WHERE ProcessName = 'sydoc.05_PDBS';
END
GO

-- (4) IndexFieldMappings: MS02 source field name -> normalized target key (used to
--     render extracted fields in the workitem detail). Insert only what is missing.
INSERT INTO dbo.IndexFieldMappings (SourceFieldName, TargetKey)
SELECT v.SourceFieldName, v.TargetKey
FROM (VALUES
    ('DossierBarcode', 'DocBarcode'),
    ('BoxNummer', 'ArchiveBoxNo'),
    ('BatchName', 'BatchName'),
    ('DossierNummer', 'PID'),
    ('DossierPositionInBatch', 'DossierPositionInBatch'),
    ('AnzahlSeitenImDossier', 'PageCount')
) AS v(SourceFieldName, TargetKey)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.IndexFieldMappings m
    WHERE m.SourceFieldName = v.SourceFieldName AND m.TargetKey = v.TargetKey
);
GO

-- (5) search_field_labels: localized labels for the new doc-field keys.
INSERT INTO dbo.search_field_labels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel)
SELECT v.FieldKey, v.EnglishLabel, v.GermanLabel, v.FrenchLabel, v.ItalianLabel
FROM (VALUES
    ('batchname', 'Batch Name', 'Stapelname', 'Nom du lot', 'Nome del lotto'),
    ('pid', 'Person ID', 'Personen-ID', 'Identifiant de la personne', 'ID persona'),
    ('dossierpositioninbatch', 'Dossier Position in Batch', 'Dossier Position in Stapel',
     'Position du dossier dans le lot', 'Posizione del dossier nel lotto'),
    ('pagecount', 'Page Count', 'Seitenzahl', 'Nombre de pages', 'Numero di pagine')
) AS v(FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.search_field_labels l WHERE l.FieldKey = v.FieldKey
);
GO
