-- 0012_documents_drop_dead_columns.sql
-- Issue #220, phase 4c: drop 17 columns from dbo.Documents.
--
-- *** DESTRUCTIVE. READ THE DEPLOY NOTE BEFORE MERGING. ***
--
-- DEPLOY NOTE -- the CSV importer is NOT deployed by deploy.yml. Both copies
-- of csvToSql.ps1 live in this repo, but the one that actually runs sits on
-- **prdimpexp01** at \\prdimpexp01\d$\sydoc\scripts\generali and is copied there
-- by hand. Phases 1-3 did not care: the compat views dbo.ReportJob and
-- dbo.CSVImportLog keep an un-updated host script working. THIS migration
-- does care -- it removes columns the old script still lists in its INSERT,
-- and no view can conjure them back. **Copy the updated csvToSql.ps1 to
-- prdimpexp01 before this reaches PROD**, or the 12:05 import fails the next
-- morning.
--
-- Measured on INT 2026-09-10 over 2,682,707 rows, immediately before writing
-- this file -- not taken from the plan, whose numbers had already moved:
--
--   0 non-null rows      DOC_JOURNAL_ID, DOC_DOKUMENT_URL, DOC_BARCODENR, DOC_PageSize
--   empty strings only   DOC_ALFpages, DOC_ALFdpages (3,719 rows, MAX(LEN) = 0)
--   0 non-null rows      DOC_SAPCompCharset, DOC_SAPCompCreated, DOC_SAPCompModified, DOC_SAPCompVersion, DOC_SAPDocDate
--   moved by 0011        DOC_SAPComps, DOC_SAPCompSize, DOC_SAPContType, DOC_SAPDocId, DOC_SAPDocProt, DOC_SAPType (3,719 rows now in
--                        dbo.DocumentSapMetadata)
--
-- NOT dropped, against the plan: **DOC_DOKUMENT_ID**. The plan listed it as
-- provably empty, and it was; it is not any more. One row written 2026-09-02
-- holds free text ("Keine aktive Policen-Nr. bekannt. Keine Schaden-Nr.
-- bekannt. Rob..."), i.e. somebody's remark in the wrong column. One row is
-- still data, and dropping data nobody authorised is not this migration's job.
-- It keeps its old name until Generali says what it is.
--
-- The three views are rebuilt without the dropped columns. v_Documents keeps
-- the four typed columns from 0010; the two compat views deliberately do not
-- show them -- they exist to look like the old world until phase 6.
--
-- Idempotent.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- Refuse to drop the SAP columns if 0011 did not actually move them.
IF OBJECT_ID(N'dbo.DocumentSapMetadata', N'U') IS NULL
    THROW 50222, 'Migration 0012: dbo.DocumentSapMetadata does not exist. Apply 0011 first.', 1;
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPDocId') IS NOT NULL
   AND (SELECT COUNT(*) FROM dbo.DocumentSapMetadata)
     < (SELECT COUNT(*) FROM dbo.Documents WHERE DOC_SAPDocId IS NOT NULL)
    THROW 50223, 'Migration 0012: DocumentSapMetadata holds fewer rows than dbo.Documents has SAP data. Re-run 0011 before dropping.', 1;
GO

-- ---------------------------------------------------------------------------
-- 1. Drop.
-- ---------------------------------------------------------------------------
IF COL_LENGTH(N'dbo.Documents', N'DOC_JOURNAL_ID') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_JOURNAL_ID];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_DOKUMENT_URL') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_DOKUMENT_URL];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_BARCODENR') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_BARCODENR];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_PageSize') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_PageSize];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_ALFpages') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_ALFpages];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_ALFdpages') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_ALFdpages];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPCompCharset') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPCompCharset];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPCompCreated') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPCompCreated];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPCompModified') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPCompModified];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPCompVersion') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPCompVersion];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPDocDate') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPDocDate];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPComps') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPComps];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPCompSize') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPCompSize];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPContType') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPContType];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPDocId') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPDocId];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPDocProt') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPDocProt];
GO
IF COL_LENGTH(N'dbo.Documents', N'DOC_SAPType') IS NOT NULL
    ALTER TABLE dbo.Documents DROP COLUMN [DOC_SAPType];
GO

-- ---------------------------------------------------------------------------
-- 2. Rebuild the three views without the dropped columns.
-- ---------------------------------------------------------------------------
CREATE OR ALTER VIEW dbo.v_Documents
AS
SELECT
    [ScanCaseId],
    [ScanCaseFolderName],
    [DocumentId],
    [EnvelopeId],
    [CaseId],
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
    [Amount],
    [CompanyCode],
    [QuantityText],
    [Quantity],
    [BusinessType],
    [ContactPerson],
    [VendorNo],
    [QuoteNo],
    [AccountNo],
    [Description],
    [PendingText],
    [IsPending],
    [VoucherDateText],
    [VoucherDate],
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

CREATE OR ALTER VIEW dbo.v_ReportJobJoinDefinitions
AS
SELECT
    [ScanCaseId] AS [CASE_ID],
    [ScanCaseFolderName] AS [CASE_FOLDERNAME],
    [DocumentId] AS [DOC_ID],
    [EnvelopeId] AS [DOC_COUVERT_ID],
    [CaseId] AS [DOC_CASE_ID],
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

CREATE OR ALTER VIEW dbo.ReportJob
AS
SELECT
    [Id] AS [RecordID],
    [ScanCaseId] AS [CASE_ID],
    [ScanCaseFolderName] AS [CASE_FOLDERNAME],
    [DocumentId] AS [DOC_ID],
    [EnvelopeId] AS [DOC_COUVERT_ID],
    [CaseId] AS [DOC_CASE_ID],
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
