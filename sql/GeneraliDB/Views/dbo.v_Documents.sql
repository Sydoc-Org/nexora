USE [Generali]
GO
DROP VIEW [dbo].[v_Documents]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- ---------------------------------------------------------------------------
-- 2. Rebuild the three views without the dropped columns.
-- ---------------------------------------------------------------------------
CREATE   VIEW [dbo].[v_Documents]
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
