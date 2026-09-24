-- 0005_english_table_names.sql
-- Issue #220, phase 2: every table gets an English, PascalCase, plural name.
-- Metadata only -- sp_rename does not move data, so this is instant even with
-- ReportJob's 2.68M rows behind the view.
--
-- Ships with the matching code change in nx_lib/views/generali/, both copies of
-- scripts/generali-import/*/csvToSql.ps1, and NexoraDB migration
-- 0128_generali_renamed_objects.sql (the reporting registry stores object names
-- as data).
--
-- COMPAT VIEWS (D8): deploy.yml applies migrations to PROD *before* it stops
-- the app pool, so for a few seconds the old code runs against the new schema.
-- Every table the application names directly therefore keeps a view under its
-- old name, mapping the old column names back. These come out in phase 6.
--
-- The 13 lookup tables deliberately get NO compat view. Nothing names them
-- directly: their only consumer is v_ReportJobJoinDefinitions, which this
-- migration rebuilds onto the new names in the same batch (verified by grep
-- across nx_lib/, templates/, static/, scripts/ and tests/, and by 31 days of
-- Query Store on INT showing no other consumer). Thirteen views nothing reads
-- would only be thirteen more things for phase 6 to drop.
--
-- ReportJob itself is NOT renamed here -- that is phase 3, together with its
-- 79 columns.
--
-- Idempotent: every step is guarded on the current name still existing.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- ---------------------------------------------------------------------------
-- 1. The 13 lookups: <German> -> <English plural>, ID -> Id, Value -> Name.
-- ---------------------------------------------------------------------------
DECLARE @lookups TABLE (old sysname, new sysname);
INSERT INTO @lookups (old, new) VALUES
    (N'DokumentenStatus',    N'DocumentStatuses'),
    (N'DokumentenTyp',       N'DocumentTypes'),
    (N'Eingangskanal',       N'InboundChannels'),
    (N'Empfaenger',          N'Recipients'),
    (N'InterfaceLink',       N'InterfaceLinks'),
    (N'Kommunikation',       N'CommunicationTypes'),
    (N'Nachkontrolle',       N'PostChecks'),
    (N'NotifikationsStatus', N'NotificationStatuses'),
    (N'Richtung',            N'Directions'),
    (N'ScanOrt',             N'ScanLocations'),
    (N'Sprache',             N'Languages'),
    (N'Ursprung',            N'Origins'),
    (N'Waehrung',            N'Currencies');

DECLARE @old sysname, @new sysname, @sql nvarchar(max);
DECLARE lk CURSOR LOCAL FAST_FORWARD FOR SELECT old, new FROM @lookups;
OPEN lk;
FETCH NEXT FROM lk INTO @old, @new;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF OBJECT_ID(N'dbo.' + QUOTENAME(@old), N'U') IS NOT NULL
       AND OBJECT_ID(N'dbo.' + QUOTENAME(@new), N'U') IS NULL
    BEGIN
        SET @sql = N'EXEC sp_rename N''dbo.' + QUOTENAME(@old) + N''', N''' + @new + N''';';
        EXEC sp_executesql @sql;
    END
    -- ID -> Id is case-only and so invisible to SQL Server's CI collation, but
    -- it is what the naming rulebook says and it is what the DDL dump records.
    IF COL_LENGTH(N'dbo.' + QUOTENAME(@new), N'Id') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM sys.columns
                       WHERE object_id = OBJECT_ID(N'dbo.' + QUOTENAME(@new))
                         AND name = N'Id' COLLATE Latin1_General_CS_AS)
    BEGIN
        SET @sql = N'EXEC sp_rename N''dbo.' + QUOTENAME(@new) + N'.ID'', N''Id'', ''COLUMN'';';
        EXEC sp_executesql @sql;
    END
    IF COL_LENGTH(N'dbo.' + QUOTENAME(@new), N'Value') IS NOT NULL
    BEGIN
        SET @sql = N'EXEC sp_rename N''dbo.' + QUOTENAME(@new) + N'.Value'', N''Name'', ''COLUMN'';';
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM lk INTO @old, @new;
END
CLOSE lk;
DEALLOCATE lk;
GO

-- ---------------------------------------------------------------------------
-- 2. The effort cluster and the import log.
--    Column renames are limited to the two genuine outliers: ReportingISS's
--    lowercase `category`, and CSVImportLog's German Min/MaxScanDatum. The rest
--    of these tables' columns are left alone -- phase 5 merges the four effort
--    tables into one EffortEntries and can name their columns then, and doing
--    it here would double the code churn for no gain.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.Attendance', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.AttendanceEntries', N'U') IS NULL
    EXEC sp_rename N'dbo.Attendance', N'AttendanceEntries';
GO
IF OBJECT_ID(N'dbo.BaseServices', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.BaseServiceEntries', N'U') IS NULL
    EXEC sp_rename N'dbo.BaseServices', N'BaseServiceEntries';
GO
IF OBJECT_ID(N'dbo.ProjectManagement', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.ProjectEntries', N'U') IS NULL
    EXEC sp_rename N'dbo.ProjectManagement', N'ProjectEntries';
GO
IF OBJECT_ID(N'dbo.PDQMReport', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.QualityCheckEntries', N'U') IS NULL
    EXEC sp_rename N'dbo.PDQMReport', N'QualityCheckEntries';
GO
IF OBJECT_ID(N'dbo.PDQMMapping', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.QualityCheckCategories', N'U') IS NULL
    EXEC sp_rename N'dbo.PDQMMapping', N'QualityCheckCategories';
GO
IF OBJECT_ID(N'dbo.AdditionalServices', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.EffortCategories', N'U') IS NULL
    EXEC sp_rename N'dbo.AdditionalServices', N'EffortCategories';
GO
IF OBJECT_ID(N'dbo.CategoryTranslation', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.CategoryTranslations', N'U') IS NULL
    EXEC sp_rename N'dbo.CategoryTranslation', N'CategoryTranslations';
GO
IF OBJECT_ID(N'dbo.ReportingISS', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.IssReports', N'U') IS NULL
    EXEC sp_rename N'dbo.ReportingISS', N'IssReports';
GO
IF COL_LENGTH(N'dbo.IssReports', N'category') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'dbo.IssReports')
                     AND name = N'Category' COLLATE Latin1_General_CS_AS)
    EXEC sp_rename N'dbo.IssReports.category', N'Category', 'COLUMN';
GO
IF OBJECT_ID(N'dbo.CSVImportLog', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.ImportRuns', N'U') IS NULL
    EXEC sp_rename N'dbo.CSVImportLog', N'ImportRuns';
GO
IF COL_LENGTH(N'dbo.ImportRuns', N'MinScanDatum') IS NOT NULL
    EXEC sp_rename N'dbo.ImportRuns.MinScanDatum', N'MinScannedAt', 'COLUMN';
GO
IF COL_LENGTH(N'dbo.ImportRuns', N'MaxScanDatum') IS NOT NULL
    EXEC sp_rename N'dbo.ImportRuns.MaxScanDatum', N'MaxScannedAt', 'COLUMN';
GO

-- CategoryTranslations.SourceTable stores table names as *data* ('AdditionalServices',
-- 'PDQMMapping'), so the rename has to reach into the rows as well.
UPDATE dbo.CategoryTranslations SET SourceTable = N'EffortCategories'
WHERE SourceTable = N'AdditionalServices';
UPDATE dbo.CategoryTranslations SET SourceTable = N'QualityCheckCategories'
WHERE SourceTable = N'PDQMMapping';
GO

-- ---------------------------------------------------------------------------
-- 3. Rebuild v_ReportJobJoinDefinitions on the new lookup names.
--    Output columns are byte-for-byte the ones it exposed before, so no
--    application code changes because of this view. Phase 3 renames the view
--    itself to v_Documents and renames these output columns with it.
--    Note the WHERE: this view has always shown only the CaptivaCapture rows
--    (890,298 of 2,682,707 on INT), which is easy to miss.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW [dbo].[v_ReportJobJoinDefinitions]
AS
SELECT
      [CASE_ID]
     ,[CASE_FOLDERNAME]
     ,[DOC_ID]
     ,[DOC_COUVERT_ID]
     ,[DOC_CASE_ID]
     ,[DOC_JOURNAL_ID]
     ,[DOC_DateCreated]
     ,[DOC_COUVERTDOCCOUNT]
     ,k.Name AS DOC_KOMMUNIKATION
     ,[DOC_INITIAL_USER]
     ,[DOC_SCANDATUM_INITIAL]
     ,[DOC_SCANDATUM]
     ,dt.Name AS DOC_DOKUMENTENTYP
     ,e.Name AS DOC_EMPFAENGER
     ,[DOC_EMPFAENGERADRESSE]
     ,spr.Name AS DOC_SPRACHE
     ,n.Name AS DOC_NOTIFIKATIONSSTATUS
     ,[DOC_VERTRAULICHKEIT]
     ,r.Name AS DOC_RICHTUNG
     ,[DOC_DOKUMENT_ID]
     ,[DOC_DOKUMENTENORDER]
     ,ds.Name AS DOC_DOKUMENTENSTATUS
     ,[DOC_DOKUMENT_URL]
     ,ek.Name AS DOC_EINGANGSKANAL
     ,[DOC_ANTRAG_NR]
     ,[DOC_ANTRAG_NR_MULTI]
     ,[DOC_PARTNER_NR_SYRIUS]
     ,[DOC_PARTNER_NR_GAV]
     ,[DOC_PARTNER_NR_GPV]
     ,[DOC_PARTNER_NR_RGI]
     ,[DOC_PRODUKT_CODE]
     ,[DOC_BEMERKUNG]
     ,so.Name AS DOC_SCANORT
     ,[DOC_SCANUSER]
     ,[DOC_FORMULAR_NR]
     ,[DOC_PERSONAL_NR]
     ,[DOC_POLICEN_NR]
     ,[DOC_POLICEN_NR_MULTI]
     ,[DOC_SCHADEN_NR]
     ,[DOC_VERFAHREN_NR]
     ,w.Name AS DOC_WAEHRUNG
     ,[DOC_BETRAG]
     ,[DOC_BUCHUNGSKREIS_NR]
     ,[DOC_ANZAHL]
     ,[DOC_GESCHAEFTSART]
     ,[DOC_KONTAKTPERSON]
     ,[DOC_KREDITOREN_NR]
     ,[DOC_OFFERTEN_NR]
     ,[DOC_KONTONUMMER]
     ,[DOC_BEZEICHNUNG]
     ,[DOC_PENDING]
     ,[DOC_ALFdpages]
     ,[DOC_ALFpages]
     ,[DOC_PageSize]
     ,[DOC_SAPCompCharset]
     ,[DOC_SAPCompCreated]
     ,[DOC_SAPCompModified]
     ,[DOC_SAPComps]
     ,[DOC_SAPCompSize]
     ,[DOC_SAPCompVersion]
     ,[DOC_SAPContType]
     ,[DOC_SAPDocDate]
     ,[DOC_SAPDocId]
     ,[DOC_SAPDocProt]
     ,[DOC_SAPType]
     ,[DOC_BARCODENR]
     ,[DOC_BELEGDATUM]
     ,[DOC_FONDSNAME]
     ,[DOC_VERTRAGSNUMMER]
     ,[DOC_VERTRAGSPARTNER]
     ,[DOC_DOSSIER_NR]
     ,[DOC_REFERENZNUMMER]
     ,u.Name AS DOC_ORIGIN
     ,ifl.Name AS DOC_INTERFACE_LINK
     ,nk1.Name AS DOC_NK1
     ,nk2.Name AS DOC_NK2
     ,SourceCSVFileName
FROM dbo.ReportJob rj
LEFT JOIN dbo.DocumentStatuses    ds  ON ds.Id  = rj.DOC_DOKUMENTENSTATUS
LEFT JOIN dbo.DocumentTypes       dt  ON dt.Id  = rj.DOC_DOKUMENTENTYP
LEFT JOIN dbo.InboundChannels     ek  ON ek.Id  = rj.DOC_EINGANGSKANAL
LEFT JOIN dbo.Recipients          e   ON e.Id   = rj.DOC_EMPFAENGER
LEFT JOIN dbo.InterfaceLinks      ifl ON ifl.Id = rj.DOC_INTERFACE_LINK
LEFT JOIN dbo.CommunicationTypes  k   ON k.Id   = rj.DOC_KOMMUNIKATION
LEFT JOIN dbo.PostChecks          nk1 ON nk1.Id = rj.DOC_NK1
LEFT JOIN dbo.PostChecks          nk2 ON nk2.Id = rj.DOC_NK2
LEFT JOIN dbo.NotificationStatuses n  ON n.Id   = rj.DOC_NOTIFIKATIONSSTATUS
LEFT JOIN dbo.Directions          r   ON r.Id   = rj.DOC_RICHTUNG
LEFT JOIN dbo.ScanLocations       so  ON so.Id  = rj.DOC_SCANORT
LEFT JOIN dbo.Languages           spr ON spr.Id = rj.DOC_SPRACHE
LEFT JOIN dbo.Origins             u   ON u.Id   = rj.DOC_ORIGIN
LEFT JOIN dbo.Currencies          w   ON w.Id   = rj.DOC_WAEHRUNG
WHERE ifl.Name = 'CaptivaCapture';
GO

-- ---------------------------------------------------------------------------
-- 4. Compat views under the old names, for the deploy window only (D8).
--    Single-table, no aggregates, so they stay updatable -- the CRUD endpoints
--    can still INSERT/UPDATE/DELETE through them if a write lands mid-deploy.
--    Phase 6 drops all nine.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW dbo.Attendance AS
SELECT ID, EffortInHours, UserID, ForDate, ParentCategory, SubCategory, RecordDateTime
FROM dbo.AttendanceEntries;
GO
CREATE OR ALTER VIEW dbo.BaseServices AS
SELECT ID, EffortInHours, UserID, ForDate, Category, RecordDateTime
FROM dbo.BaseServiceEntries;
GO
CREATE OR ALTER VIEW dbo.ProjectManagement AS
SELECT ID, EffortInHours, UserID, ForDate, Category, Comment, RecordDateTime
FROM dbo.ProjectEntries;
GO
CREATE OR ALTER VIEW dbo.PDQMReport AS
SELECT ID, Quantity, ForDate, UserID, RecordDateTime, ParentCategory, ParentSubCategory, SubCategory
FROM dbo.QualityCheckEntries;
GO
CREATE OR ALTER VIEW dbo.PDQMMapping AS
SELECT ID, ParentCategory, ParentSubCategory, SubCategory
FROM dbo.QualityCheckCategories;
GO
CREATE OR ALTER VIEW dbo.AdditionalServices AS
SELECT ID, SubCategory, ParentCategory
FROM dbo.EffortCategories;
GO
CREATE OR ALTER VIEW dbo.ReportingISS AS
SELECT ID, ReportForDate, ReportTimeStamp, ReportByUserID, OnTime, Category AS category
FROM dbo.IssReports;
GO
CREATE OR ALTER VIEW dbo.CSVImportLog AS
SELECT ID, FileName, StartedAt, FinishedAt, CSVRowCount, RowsInserted, RowsUpdated,
       MinScannedAt AS MinScanDatum, MaxScannedAt AS MaxScanDatum, [Status]
FROM dbo.ImportRuns;
GO
-- SourceTable values moved with the tables above, so old code reading this view
-- finds no rows for 'AdditionalServices' / 'PDQMMapping' and falls back to the
-- untranslated German labels for the few seconds of the deploy window.
CREATE OR ALTER VIEW dbo.CategoryTranslation AS
SELECT ID, SourceTable, OriginalValue, Locale, TranslatedValue
FROM dbo.CategoryTranslations;
GO

-- ---------------------------------------------------------------------------
-- 5. Constraint names follow the tables. Same catalog-driven block as 0004:
--    matched by table and column, never by the current name.
-- ---------------------------------------------------------------------------
SET NOCOUNT ON;

DECLARE @rename nvarchar(max) = N'';

SELECT @rename = @rename
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(kc.name) + N''', N''PK_' + t.name + N''', ''OBJECT'';' + CHAR(10)
FROM sys.key_constraints kc
JOIN sys.tables t ON t.object_id = kc.parent_object_id
WHERE kc.type = 'PK' AND kc.name <> N'PK_' + t.name;

SELECT @rename = @rename
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(f.fk_name) + N''', N''' + f.target + N''', ''OBJECT'';' + CHAR(10)
FROM (
    SELECT fk.name AS fk_name,
           N'FK_' + pt.name + N'_' + rt.name
             + CASE WHEN COUNT(*) OVER (PARTITION BY fk.parent_object_id, fk.referenced_object_id) > 1
                    THEN N'_' + CASE WHEN pc.name LIKE 'DOC[_]%' THEN STUFF(pc.name, 1, 4, N'') ELSE pc.name END
                    ELSE N'' END AS target
    FROM sys.foreign_keys fk
    JOIN sys.tables pt ON pt.object_id = fk.parent_object_id
    JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
    JOIN sys.foreign_key_columns fkc
      ON fkc.constraint_object_id = fk.object_id AND fkc.constraint_column_id = 1
    JOIN sys.columns pc
      ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
) AS f
WHERE f.fk_name <> f.target;

SELECT @rename = @rename
     + N'EXEC sp_rename N''dbo.' + QUOTENAME(dc.name) + N''', N''DF_' + t.name + N'_' + c.name + N''', ''OBJECT'';' + CHAR(10)
FROM sys.default_constraints dc
JOIN sys.tables t ON t.object_id = dc.parent_object_id
JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
WHERE dc.name <> N'DF_' + t.name + N'_' + c.name;

IF @rename = N''
    PRINT 'Migration 0005: constraint names already match their tables.';
ELSE
BEGIN
    PRINT @rename;
    EXEC sp_executesql @rename;
END
GO
