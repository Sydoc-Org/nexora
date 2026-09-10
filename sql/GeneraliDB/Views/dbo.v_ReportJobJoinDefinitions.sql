USE [Generali]
GO
DROP VIEW [dbo].[v_ReportJobJoinDefinitions]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

CREATE   VIEW [dbo].[v_ReportJobJoinDefinitions]
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
