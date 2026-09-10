USE [Generali]
GO
DROP VIEW [dbo].[ReportJob]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- ---------------------------------------------------------------------------
-- 6. Compat: the old table name and old column names, updatable, for the
--    seconds of the deploy window in which PROD's old importer and old app
--    code meet the new schema.
-- ---------------------------------------------------------------------------
CREATE   VIEW [dbo].[ReportJob]
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
