-- 0007_reportjob_to_documents.sql
-- Issue #220, phase 3: dbo.ReportJob becomes dbo.Documents and 61 of its 79
-- columns get English, PascalCase, un-prefixed names. sp_rename only -- this is
-- metadata, so it is instant even at 2.68M rows, and no data is touched.
--
-- Ships with the matching code change in nx_lib/views/generali/documents.py,
-- both copies of scripts/generali-import/*/csvToSql.ps1, and NexoraDB migration
-- 0129_generali_documents_renamed_fields.sql.
--
-- WHAT IS *NOT* RENAMED, on purpose (18 columns): the five provably-dead ones
-- (DOC_JOURNAL_ID, DOC_DOKUMENT_ID, DOC_DOKUMENT_URL, DOC_BARCODENR,
-- DOC_PageSize -- 0 non-null rows out of 2.68M), the two empty-string ones
-- (DOC_ALFpages, DOC_ALFdpages) and the whole 11-column DOC_SAP* block. Phase 4
-- drops the first seven, drops six of the SAP columns and moves the other five
-- into DocumentSapMetadata with proper names. Renaming a column on its way to
-- the bin is work done twice.
--
-- FOUR ...Text NAMES ARE DELIBERATE (D7). DOC_BETRAG -> AmountText,
-- DOC_ANZAHL -> QuantityText, DOC_PENDING -> PendingText,
-- DOC_BELEGDATUM -> VoucherDateText. Phase 4 adds a real `Amount decimal(18,2)`,
-- `Quantity int`, `IsPending bit` and `VoucherDate date` *beside* them, because
-- 12,284 of the 12,491 DOC_BETRAG values do not parse as decimal and a blind
-- ALTER COLUMN would silently zero the only money in the database. The plain
-- names are reserved for the typed columns.
--
-- Q2 answered by the owner 2026-09-10: CASE_ID -> ScanCaseId (a GUID scan
-- batch id, always paired with CASE_FOLDERNAME, 29,760 rows, EARLY SCANNING
-- only) and DOC_CASE_ID -> CaseId (a `CID001126050` business reference, 1,741
-- rows). They are never both set.
--
-- THREE VIEWS AFTERWARDS:
--   dbo.Documents                    the table
--   dbo.v_Documents                  the new canonical read view -- lookups
--                                    resolved to text, English column names
--   dbo.v_ReportJobJoinDefinitions   compat: v_Documents under the old output
--                                    names, so nothing outside this commit has
--                                    to move at once
--   dbo.ReportJob                    compat: the table under its old column
--                                    names, updatable, so the importer still
--                                    works during the deploy window (D8 --
--                                    deploy.yml migrates PROD *before* it stops
--                                    the app pool)
-- Both compat views come down in phase 6.
--
-- Idempotent: every rename is guarded on the old name still being there.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- ---------------------------------------------------------------------------
-- 1. The table.
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.ReportJob', N'U') IS NOT NULL AND OBJECT_ID(N'dbo.Documents', N'U') IS NULL
    EXEC sp_rename N'dbo.ReportJob', N'Documents';
GO

-- ---------------------------------------------------------------------------
-- 1b. UQ_ReportJob_DOC_ID has to go before DOC_ID can be renamed.
--     A filtered index's predicate is a real dependency: sp_rename on a column
--     a filter references fails with "The object is dependent on column"
--     (Msg 5074 / 4922). Every other index tracks columns by id and follows the
--     rename by itself. Section 3 recreates this one on the new name -- ~9 s
--     to rebuild on 2.68M rows, and there is a window inside this migration in
--     which DocumentId is not unique-indexed. That is acceptable here: the
--     importer runs at 12:05 and a deploy does not.
-- ---------------------------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.indexes
           WHERE object_id = OBJECT_ID(N'dbo.Documents') AND name = N'UQ_ReportJob_DOC_ID')
    DROP INDEX UQ_ReportJob_DOC_ID ON dbo.Documents;
GO

-- ---------------------------------------------------------------------------
-- 2. The 61 columns.
-- ---------------------------------------------------------------------------
DECLARE @cols TABLE (old sysname, new sysname);
INSERT INTO @cols (old, new) VALUES
    (N'RecordID', N'Id'),
    (N'CASE_ID', N'ScanCaseId'),
    (N'CASE_FOLDERNAME', N'ScanCaseFolderName'),
    (N'DOC_ID', N'DocumentId'),
    (N'DOC_COUVERT_ID', N'EnvelopeId'),
    (N'DOC_CASE_ID', N'CaseId'),
    (N'DOC_DateCreated', N'CreatedAt'),
    (N'DOC_COUVERTDOCCOUNT', N'EnvelopeDocumentCount'),
    (N'DOC_KOMMUNIKATION', N'CommunicationTypeId'),
    (N'DOC_INITIAL_USER', N'InitialUser'),
    (N'DOC_SCANDATUM_INITIAL', N'InitialScannedAt'),
    (N'DOC_SCANDATUM', N'ScannedAt'),
    (N'DOC_DOKUMENTENTYP', N'DocumentTypeId'),
    (N'DOC_EMPFAENGER', N'RecipientId'),
    (N'DOC_EMPFAENGERADRESSE', N'RecipientAddress'),
    (N'DOC_SPRACHE', N'LanguageId'),
    (N'DOC_NOTIFIKATIONSSTATUS', N'NotificationStatusId'),
    (N'DOC_VERTRAULICHKEIT', N'ConfidentialityCode'),
    (N'DOC_RICHTUNG', N'DirectionId'),
    (N'DOC_DOKUMENTENORDER', N'DocumentOrder'),
    (N'DOC_DOKUMENTENSTATUS', N'DocumentStatusId'),
    (N'DOC_EINGANGSKANAL', N'InboundChannelId'),
    (N'DOC_ANTRAG_NR', N'ApplicationNo'),
    (N'DOC_ANTRAG_NR_MULTI', N'ApplicationNos'),
    (N'DOC_PARTNER_NR_SYRIUS', N'PartnerNoSyrius'),
    (N'DOC_PARTNER_NR_GAV', N'PartnerNoGav'),
    (N'DOC_PARTNER_NR_GPV', N'PartnerNoGpv'),
    (N'DOC_PARTNER_NR_RGI', N'PartnerNoRgi'),
    (N'DOC_PRODUKT_CODE', N'ProductCode'),
    (N'DOC_BEMERKUNG', N'Remark'),
    (N'DOC_SCANORT', N'ScanLocationId'),
    (N'DOC_SCANUSER', N'ScanUser'),
    (N'DOC_FORMULAR_NR', N'FormNo'),
    (N'DOC_PERSONAL_NR', N'PersonnelNo'),
    (N'DOC_POLICEN_NR', N'PolicyNo'),
    (N'DOC_POLICEN_NR_MULTI', N'PolicyNos'),
    (N'DOC_SCHADEN_NR', N'ClaimNo'),
    (N'DOC_VERFAHREN_NR', N'ProceedingNo'),
    (N'DOC_WAEHRUNG', N'CurrencyId'),
    (N'DOC_BETRAG', N'AmountText'),
    (N'DOC_BUCHUNGSKREIS_NR', N'CompanyCode'),
    (N'DOC_ANZAHL', N'QuantityText'),
    (N'DOC_GESCHAEFTSART', N'BusinessType'),
    (N'DOC_KONTAKTPERSON', N'ContactPerson'),
    (N'DOC_KREDITOREN_NR', N'VendorNo'),
    (N'DOC_OFFERTEN_NR', N'QuoteNo'),
    (N'DOC_KONTONUMMER', N'AccountNo'),
    (N'DOC_BEZEICHNUNG', N'Description'),
    (N'DOC_PENDING', N'PendingText'),
    (N'DOC_BELEGDATUM', N'VoucherDateText'),
    (N'DOC_FONDSNAME', N'FundName'),
    (N'DOC_VERTRAGSNUMMER', N'ContractNo'),
    (N'DOC_VERTRAGSPARTNER', N'ContractPartner'),
    (N'DOC_DOSSIER_NR', N'DossierNo'),
    (N'DOC_REFERENZNUMMER', N'ReferenceNo'),
    (N'DOC_ORIGIN', N'OriginId'),
    (N'DOC_INTERFACE_LINK', N'InterfaceLinkId'),
    (N'DOC_NK1', N'PostCheck1Id'),
    (N'DOC_NK2', N'PostCheck2Id'),
    (N'InsertedAt', N'ImportedAt'),
    (N'SourceCSVFileName', N'SourceCsvFileName');

DECLARE @old sysname, @new sysname, @sql nvarchar(max);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT old, new FROM @cols;
OPEN c;
FETCH NEXT FROM c INTO @old, @new;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF COL_LENGTH(N'dbo.Documents', @old) IS NOT NULL
       AND COL_LENGTH(N'dbo.Documents', @new) IS NULL
    BEGIN
        SET @sql = N'EXEC sp_rename N''dbo.Documents.' + QUOTENAME(@old) + N''', N''' + @new + N''', ''COLUMN'';';
        EXEC sp_executesql @sql;
    END
    FETCH NEXT FROM c INTO @old, @new;
END
CLOSE c;
DEALLOCATE c;
GO

-- ---------------------------------------------------------------------------
-- 3. The two indexes from 0003 follow the names they index. The unique one is
--    recreated rather than renamed (see 1b); the covering one just gets a new
--    name, its key and INCLUDE list having followed the column renames.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.Documents') AND name = N'UQ_Documents_DocumentId')
    CREATE UNIQUE NONCLUSTERED INDEX UQ_Documents_DocumentId
        ON dbo.Documents (DocumentId)
        WHERE DocumentId IS NOT NULL;
GO
IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.Documents') AND name = N'IX_ReportJob_DOC_SCANDATUM')
    EXEC sp_rename N'dbo.Documents.IX_ReportJob_DOC_SCANDATUM', N'IX_Documents_ScannedAt', 'INDEX';
GO

-- ---------------------------------------------------------------------------
-- 4. v_Documents -- the new canonical read view. Same 77 output columns as the
--    old view had, same CaptivaCapture filter (890,298 of 2,682,707 rows),
--    English names throughout.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW dbo.v_Documents
AS
SELECT
    [ScanCaseId],
    [ScanCaseFolderName],
    [DocumentId],
    [EnvelopeId],
    [CaseId],
    [DOC_JOURNAL_ID],
    [CreatedAt],
    [EnvelopeDocumentCount],
    k.Name AS [CommunicationType],
    [InitialUser],
    [InitialScannedAt],
    [ScannedAt],
    dt.Name AS [DocumentType],
    e.Name AS [Recipient],
    [RecipientAddress],
    spr.Name AS [Language],
    n.Name AS [NotificationStatus],
    [ConfidentialityCode],
    r.Name AS [Direction],
    [DOC_DOKUMENT_ID],
    [DocumentOrder],
    ds.Name AS [DocumentStatus],
    [DOC_DOKUMENT_URL],
    ek.Name AS [InboundChannel],
    [ApplicationNo],
    [ApplicationNos],
    [PartnerNoSyrius],
    [PartnerNoGav],
    [PartnerNoGpv],
    [PartnerNoRgi],
    [ProductCode],
    [Remark],
    so.Name AS [ScanLocation],
    [ScanUser],
    [FormNo],
    [PersonnelNo],
    [PolicyNo],
    [PolicyNos],
    [ClaimNo],
    [ProceedingNo],
    w.Name AS [Currency],
    [AmountText],
    [CompanyCode],
    [QuantityText],
    [BusinessType],
    [ContactPerson],
    [VendorNo],
    [QuoteNo],
    [AccountNo],
    [Description],
    [PendingText],
    [DOC_ALFdpages],
    [DOC_ALFpages],
    [DOC_PageSize],
    [DOC_SAPCompCharset],
    [DOC_SAPCompCreated],
    [DOC_SAPCompModified],
    [DOC_SAPComps],
    [DOC_SAPCompSize],
    [DOC_SAPCompVersion],
    [DOC_SAPContType],
    [DOC_SAPDocDate],
    [DOC_SAPDocId],
    [DOC_SAPDocProt],
    [DOC_SAPType],
    [DOC_BARCODENR],
    [VoucherDateText],
    [FundName],
    [ContractNo],
    [ContractPartner],
    [DossierNo],
    [ReferenceNo],
    u.Name AS [Origin],
    ifl.Name AS [InterfaceLink],
    nk1.Name AS [PostCheck1],
    nk2.Name AS [PostCheck2],
    [SourceCsvFileName]
FROM dbo.Documents d
LEFT JOIN dbo.CommunicationTypes     k    ON k.Id = d.CommunicationTypeId
LEFT JOIN dbo.DocumentTypes          dt   ON dt.Id = d.DocumentTypeId
LEFT JOIN dbo.Recipients             e    ON e.Id = d.RecipientId
LEFT JOIN dbo.Languages              spr  ON spr.Id = d.LanguageId
LEFT JOIN dbo.NotificationStatuses   n    ON n.Id = d.NotificationStatusId
LEFT JOIN dbo.Directions             r    ON r.Id = d.DirectionId
LEFT JOIN dbo.DocumentStatuses       ds   ON ds.Id = d.DocumentStatusId
LEFT JOIN dbo.InboundChannels        ek   ON ek.Id = d.InboundChannelId
LEFT JOIN dbo.ScanLocations          so   ON so.Id = d.ScanLocationId
LEFT JOIN dbo.Currencies             w    ON w.Id = d.CurrencyId
LEFT JOIN dbo.Origins                u    ON u.Id = d.OriginId
LEFT JOIN dbo.InterfaceLinks         ifl  ON ifl.Id = d.InterfaceLinkId
LEFT JOIN dbo.PostChecks             nk1  ON nk1.Id = d.PostCheck1Id
LEFT JOIN dbo.PostChecks             nk2  ON nk2.Id = d.PostCheck2Id
WHERE ifl.Name = 'CaptivaCapture';
GO

-- ---------------------------------------------------------------------------
-- 5. Compat: the old view name, old output columns, over v_Documents.
--    The reporting source generali_documents and any saved report definition
--    keep working unchanged until 0129 moves them.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW dbo.v_ReportJobJoinDefinitions
AS
SELECT
    [ScanCaseId] AS [CASE_ID],
    [ScanCaseFolderName] AS [CASE_FOLDERNAME],
    [DocumentId] AS [DOC_ID],
    [EnvelopeId] AS [DOC_COUVERT_ID],
    [CaseId] AS [DOC_CASE_ID],
    [DOC_JOURNAL_ID],
    [CreatedAt] AS [DOC_DateCreated],
    [EnvelopeDocumentCount] AS [DOC_COUVERTDOCCOUNT],
    [CommunicationType] AS [DOC_KOMMUNIKATION],
    [InitialUser] AS [DOC_INITIAL_USER],
    [InitialScannedAt] AS [DOC_SCANDATUM_INITIAL],
    [ScannedAt] AS [DOC_SCANDATUM],
    [DocumentType] AS [DOC_DOKUMENTENTYP],
    [Recipient] AS [DOC_EMPFAENGER],
    [RecipientAddress] AS [DOC_EMPFAENGERADRESSE],
    [Language] AS [DOC_SPRACHE],
    [NotificationStatus] AS [DOC_NOTIFIKATIONSSTATUS],
    [ConfidentialityCode] AS [DOC_VERTRAULICHKEIT],
    [Direction] AS [DOC_RICHTUNG],
    [DOC_DOKUMENT_ID],
    [DocumentOrder] AS [DOC_DOKUMENTENORDER],
    [DocumentStatus] AS [DOC_DOKUMENTENSTATUS],
    [DOC_DOKUMENT_URL],
    [InboundChannel] AS [DOC_EINGANGSKANAL],
    [ApplicationNo] AS [DOC_ANTRAG_NR],
    [ApplicationNos] AS [DOC_ANTRAG_NR_MULTI],
    [PartnerNoSyrius] AS [DOC_PARTNER_NR_SYRIUS],
    [PartnerNoGav] AS [DOC_PARTNER_NR_GAV],
    [PartnerNoGpv] AS [DOC_PARTNER_NR_GPV],
    [PartnerNoRgi] AS [DOC_PARTNER_NR_RGI],
    [ProductCode] AS [DOC_PRODUKT_CODE],
    [Remark] AS [DOC_BEMERKUNG],
    [ScanLocation] AS [DOC_SCANORT],
    [ScanUser] AS [DOC_SCANUSER],
    [FormNo] AS [DOC_FORMULAR_NR],
    [PersonnelNo] AS [DOC_PERSONAL_NR],
    [PolicyNo] AS [DOC_POLICEN_NR],
    [PolicyNos] AS [DOC_POLICEN_NR_MULTI],
    [ClaimNo] AS [DOC_SCHADEN_NR],
    [ProceedingNo] AS [DOC_VERFAHREN_NR],
    [Currency] AS [DOC_WAEHRUNG],
    [AmountText] AS [DOC_BETRAG],
    [CompanyCode] AS [DOC_BUCHUNGSKREIS_NR],
    [QuantityText] AS [DOC_ANZAHL],
    [BusinessType] AS [DOC_GESCHAEFTSART],
    [ContactPerson] AS [DOC_KONTAKTPERSON],
    [VendorNo] AS [DOC_KREDITOREN_NR],
    [QuoteNo] AS [DOC_OFFERTEN_NR],
    [AccountNo] AS [DOC_KONTONUMMER],
    [Description] AS [DOC_BEZEICHNUNG],
    [PendingText] AS [DOC_PENDING],
    [DOC_ALFdpages],
    [DOC_ALFpages],
    [DOC_PageSize],
    [DOC_SAPCompCharset],
    [DOC_SAPCompCreated],
    [DOC_SAPCompModified],
    [DOC_SAPComps],
    [DOC_SAPCompSize],
    [DOC_SAPCompVersion],
    [DOC_SAPContType],
    [DOC_SAPDocDate],
    [DOC_SAPDocId],
    [DOC_SAPDocProt],
    [DOC_SAPType],
    [DOC_BARCODENR],
    [VoucherDateText] AS [DOC_BELEGDATUM],
    [FundName] AS [DOC_FONDSNAME],
    [ContractNo] AS [DOC_VERTRAGSNUMMER],
    [ContractPartner] AS [DOC_VERTRAGSPARTNER],
    [DossierNo] AS [DOC_DOSSIER_NR],
    [ReferenceNo] AS [DOC_REFERENZNUMMER],
    [Origin] AS [DOC_ORIGIN],
    [InterfaceLink] AS [DOC_INTERFACE_LINK],
    [PostCheck1] AS [DOC_NK1],
    [PostCheck2] AS [DOC_NK2],
    [SourceCsvFileName] AS [SourceCSVFileName]
FROM dbo.v_Documents;
GO

-- ---------------------------------------------------------------------------
-- 6. Compat: the old table name and old column names, updatable, for the
--    seconds of the deploy window in which PROD's old importer and old app
--    code meet the new schema.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW dbo.ReportJob
AS
SELECT
    [Id] AS [RecordID],
    [ScanCaseId] AS [CASE_ID],
    [ScanCaseFolderName] AS [CASE_FOLDERNAME],
    [DocumentId] AS [DOC_ID],
    [EnvelopeId] AS [DOC_COUVERT_ID],
    [CaseId] AS [DOC_CASE_ID],
    [DOC_JOURNAL_ID],
    [CreatedAt] AS [DOC_DateCreated],
    [EnvelopeDocumentCount] AS [DOC_COUVERTDOCCOUNT],
    [CommunicationTypeId] AS [DOC_KOMMUNIKATION],
    [InitialUser] AS [DOC_INITIAL_USER],
    [InitialScannedAt] AS [DOC_SCANDATUM_INITIAL],
    [ScannedAt] AS [DOC_SCANDATUM],
    [DocumentTypeId] AS [DOC_DOKUMENTENTYP],
    [RecipientId] AS [DOC_EMPFAENGER],
    [RecipientAddress] AS [DOC_EMPFAENGERADRESSE],
    [LanguageId] AS [DOC_SPRACHE],
    [NotificationStatusId] AS [DOC_NOTIFIKATIONSSTATUS],
    [ConfidentialityCode] AS [DOC_VERTRAULICHKEIT],
    [DirectionId] AS [DOC_RICHTUNG],
    [DOC_DOKUMENT_ID],
    [DocumentOrder] AS [DOC_DOKUMENTENORDER],
    [DocumentStatusId] AS [DOC_DOKUMENTENSTATUS],
    [DOC_DOKUMENT_URL],
    [InboundChannelId] AS [DOC_EINGANGSKANAL],
    [ApplicationNo] AS [DOC_ANTRAG_NR],
    [ApplicationNos] AS [DOC_ANTRAG_NR_MULTI],
    [PartnerNoSyrius] AS [DOC_PARTNER_NR_SYRIUS],
    [PartnerNoGav] AS [DOC_PARTNER_NR_GAV],
    [PartnerNoGpv] AS [DOC_PARTNER_NR_GPV],
    [PartnerNoRgi] AS [DOC_PARTNER_NR_RGI],
    [ProductCode] AS [DOC_PRODUKT_CODE],
    [Remark] AS [DOC_BEMERKUNG],
    [ScanLocationId] AS [DOC_SCANORT],
    [ScanUser] AS [DOC_SCANUSER],
    [FormNo] AS [DOC_FORMULAR_NR],
    [PersonnelNo] AS [DOC_PERSONAL_NR],
    [PolicyNo] AS [DOC_POLICEN_NR],
    [PolicyNos] AS [DOC_POLICEN_NR_MULTI],
    [ClaimNo] AS [DOC_SCHADEN_NR],
    [ProceedingNo] AS [DOC_VERFAHREN_NR],
    [CurrencyId] AS [DOC_WAEHRUNG],
    [AmountText] AS [DOC_BETRAG],
    [CompanyCode] AS [DOC_BUCHUNGSKREIS_NR],
    [QuantityText] AS [DOC_ANZAHL],
    [BusinessType] AS [DOC_GESCHAEFTSART],
    [ContactPerson] AS [DOC_KONTAKTPERSON],
    [VendorNo] AS [DOC_KREDITOREN_NR],
    [QuoteNo] AS [DOC_OFFERTEN_NR],
    [AccountNo] AS [DOC_KONTONUMMER],
    [Description] AS [DOC_BEZEICHNUNG],
    [PendingText] AS [DOC_PENDING],
    [DOC_ALFdpages],
    [DOC_ALFpages],
    [DOC_PageSize],
    [DOC_SAPCompCharset],
    [DOC_SAPCompCreated],
    [DOC_SAPCompModified],
    [DOC_SAPComps],
    [DOC_SAPCompSize],
    [DOC_SAPCompVersion],
    [DOC_SAPContType],
    [DOC_SAPDocDate],
    [DOC_SAPDocId],
    [DOC_SAPDocProt],
    [DOC_SAPType],
    [DOC_BARCODENR],
    [VoucherDateText] AS [DOC_BELEGDATUM],
    [FundName] AS [DOC_FONDSNAME],
    [ContractNo] AS [DOC_VERTRAGSNUMMER],
    [ContractPartner] AS [DOC_VERTRAGSPARTNER],
    [DossierNo] AS [DOC_DOSSIER_NR],
    [ReferenceNo] AS [DOC_REFERENZNUMMER],
    [OriginId] AS [DOC_ORIGIN],
    [InterfaceLinkId] AS [DOC_INTERFACE_LINK],
    [PostCheck1Id] AS [DOC_NK1],
    [PostCheck2Id] AS [DOC_NK2],
    [ImportedAt] AS [InsertedAt],
    [SourceCsvFileName] AS [SourceCSVFileName]
FROM dbo.Documents;
GO

-- ---------------------------------------------------------------------------
-- 7. Constraint names follow the table. Same catalog-driven block as 0004/0005,
--    matched by table and column and never by the current name -- except that
--    a role suffix now also drops a trailing "Id" (PostCheck1Id -> PostCheck1),
--    so the two post-check keys read as FK_Documents_PostChecks_PostCheck1/2.
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
                    THEN N'_' + CASE WHEN pc.name LIKE '%Id' AND LEN(pc.name) > 2
                                     THEN LEFT(pc.name, LEN(pc.name) - 2) ELSE pc.name END
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
    PRINT 'Migration 0007: constraint names already match their tables.';
ELSE
BEGIN
    PRINT @rename;
    EXEC sp_executesql @rename;
END
GO
