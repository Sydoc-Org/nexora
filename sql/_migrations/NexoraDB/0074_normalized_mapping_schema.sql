-- 0074: normalized doc-field / process mapping schema (#98 phase 2).
-- Replaces the wide SearchConfig (one col_* column per semantic field, DDL
-- migration per new field), the PK-less StatConfig heap, IndexFieldMappings
-- (no unique key -- the 0052 dup-override trap) and Search_Field_Labels.
-- The legacy tables STAY LIVE until every consumer reads the new tables
-- through nx_lib/mapping_config.py; 0075 then decapitates them.
--
-- Backfill is in-place from the legacy rows (each environment self-backfills)
-- and guarded on the target being empty, so the pre-commit hook can re-apply
-- this file. Verified on INT + PROD 2026-08-26: SearchConfig and StatConfig
-- agree on TableName for all 6 (ProcessName, ClientCode) rows, so they merge
-- into one ProcessSources row losslessly.

IF OBJECT_ID('dbo.ProcessSources', 'U') IS NULL
CREATE TABLE dbo.ProcessSources (
    ClientCode           NVARCHAR(50)  NOT NULL,
    ProcessName          NVARCHAR(100) NOT NULL,
    TableName            NVARCHAR(100) NULL,
    TableAlias           NVARCHAR(10)  NULL,
    JoinCondition        NVARCHAR(255) NULL,
    TimeFilter            NVARCHAR(255) NULL,
    SuggestionTimeFilter NVARCHAR(255) NULL,
    ExportColumn         NVARCHAR(100) NULL,
    ImportColumn         NVARCHAR(100) NULL,
    WorkitemColumn       NVARCHAR(100) NULL,
    ExtraCondition       NVARCHAR(100) NULL,
    IdColumnType         NVARCHAR(30)  NULL,  -- seeded by 0076; NULL = legacy ::text path
    CONSTRAINT PK_ProcessSources PRIMARY KEY CLUSTERED (ClientCode, ProcessName)
);
GO

IF OBJECT_ID('dbo.FieldLabels', 'U') IS NULL
CREATE TABLE dbo.FieldLabels (
    FieldKey     NVARCHAR(100) NOT NULL,
    EnglishLabel NVARCHAR(200) NOT NULL,
    GermanLabel  NVARCHAR(200) NULL,
    FrenchLabel  NVARCHAR(200) NULL,
    ItalianLabel NVARCHAR(200) NULL,
    IsSensitive  BIT NOT NULL CONSTRAINT DF_FieldLabels_IsSensitive DEFAULT (0),
    CONSTRAINT PK_FieldLabels PRIMARY KEY CLUSTERED (FieldKey)
);
GO

IF OBJECT_ID('dbo.ProcessFieldMappings', 'U') IS NULL
CREATE TABLE dbo.ProcessFieldMappings (
    ClientCode  NVARCHAR(50)  NOT NULL,
    ProcessName NVARCHAR(100) NOT NULL,
    FieldKey    NVARCHAR(100) NOT NULL,
    ColumnName  NVARCHAR(100) NOT NULL,
    ColumnType  NVARCHAR(30)  NULL,  -- native type in the target DB; seeded by 0076
    CONSTRAINT PK_ProcessFieldMappings PRIMARY KEY CLUSTERED (ClientCode, ProcessName, FieldKey),
    CONSTRAINT FK_ProcessFieldMappings_ProcessSources
        FOREIGN KEY (ClientCode, ProcessName)
        REFERENCES dbo.ProcessSources (ClientCode, ProcessName)
);
GO

IF OBJECT_ID('dbo.FieldAliases', 'U') IS NULL
CREATE TABLE dbo.FieldAliases (
    SourceFieldName NVARCHAR(100) NOT NULL,
    TargetKey       NVARCHAR(100) NOT NULL,
    CONSTRAINT PK_FieldAliases PRIMARY KEY CLUSTERED (SourceFieldName)
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ProcessSources)
INSERT INTO dbo.ProcessSources (ClientCode, ProcessName, TableName, TableAlias, JoinCondition,
    TimeFilter, SuggestionTimeFilter, ExportColumn, ImportColumn, WorkitemColumn, ExtraCondition)
SELECT COALESCE(s.ClientCode, c.ClientCode),
       COALESCE(s.ProcessName, c.ProcessName),
       COALESCE(s.TableName, c.TableName),
       s.TableAlias, s.JoinCondition, s.TimeFilter, s.SuggestionTimeFilter,
       c.ExportColumn, c.ImportColumn, c.WorkitemColumn, c.additionalCondition
FROM dbo.SearchConfig s
FULL OUTER JOIN dbo.StatConfig c
  ON c.ProcessName = s.ProcessName AND c.ClientCode = s.ClientCode;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.FieldLabels)
INSERT INTO dbo.FieldLabels (FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive)
SELECT FieldKey, EnglishLabel, GermanLabel, FrenchLabel, ItalianLabel, IsSensitive
FROM dbo.Search_Field_Labels;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.FieldAliases)
INSERT INTO dbo.FieldAliases (SourceFieldName, TargetKey)
SELECT SourceFieldName, MIN(TargetKey)
FROM dbo.IndexFieldMappings
GROUP BY SourceFieldName;  -- dups were repaired in 0052; GROUP BY is belt-and-braces
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ProcessFieldMappings)
INSERT INTO dbo.ProcessFieldMappings (ClientCode, ProcessName, FieldKey, ColumnName)
SELECT s.ClientCode, s.ProcessName, v.FieldKey, v.ColumnName
FROM dbo.SearchConfig s
CROSS APPLY (VALUES
    ('doctype', s.col_doctype), ('docbarcode', s.col_docbarcode), ('crdno', s.col_crdno),
    ('crdname', s.col_crdname), ('bankpk', s.col_bankpk), ('grossamount', s.col_grossamount),
    ('netamount', s.col_netamount), ('vatamount', s.col_vatamount), ('doccurrency', s.col_doccurrency),
    ('invoicenr', s.col_invoicenr), ('istec', s.col_istec), ('esrreference', s.col_esrreference),
    ('ordernumber', s.col_ordernumber), ('client', s.col_client), ('docsource', s.col_docsource),
    ('ownernr', s.col_ownernr), ('tenancynr', s.col_tenancynr), ('registered', s.col_registered),
    ('branch', s.col_branch), ('docdate', s.col_docdate), ('forwarding', s.col_forwarding),
    ('department', s.col_department), ('postcode', s.col_postcode), ('recipient', s.col_recipient),
    ('confidentiality', s.col_confidentiality), ('propertynr', s.col_propertynr),
    ('separatorsheet', s.col_separatorsheet), ('docid', s.col_docid),
    ('archiveboxno', s.col_archiveboxno), ('targetsystemfilename', s.col_targetsystemfilename),
    ('emailfromaddress', s.col_emailfromaddress), ('batchname', s.col_batchname),
    ('pid', s.col_pid), ('dossierpositioninbatch', s.col_dossierpositioninbatch),
    ('pagecount', s.col_pagecount), ('validationuser', s.col_validationuser)
) AS v(FieldKey, ColumnName)
WHERE v.ColumnName IS NOT NULL;
GO
