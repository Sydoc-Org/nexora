USE [Generali]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_ScanLocations]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_Recipients]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_PostChecks_PostCheck2]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_PostChecks_PostCheck1]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_Origins]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_NotificationStatuses]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_Languages]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_InterfaceLinks]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_InboundChannels]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_DocumentTypes]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_DocumentStatuses]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_Directions]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_Currencies]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [FK_Documents_CommunicationTypes]
GO
ALTER TABLE [dbo].[Documents] DROP CONSTRAINT [DF_Documents_ImportedAt]
GO
DROP INDEX [UQ_Documents_DocumentId] ON [dbo].[Documents]
GO
DROP INDEX [IX_Documents_ScannedAt] ON [dbo].[Documents]
GO
DROP TABLE [dbo].[Documents]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Documents](
	[Id] [int] IDENTITY(1,1) NOT NULL,
	[ScanCaseId] [varchar](100) NULL,
	[ScanCaseFolderName] [varchar](100) NULL,
	[DocumentId] [varchar](100) NULL,
	[EnvelopeId] [varchar](100) NULL,
	[CaseId] [varchar](100) NULL,
	[CreatedAt] [datetime] NULL,
	[EnvelopeDocumentCount] [int] NULL,
	[CommunicationTypeId] [int] NULL,
	[InitialUser] [varchar](100) NULL,
	[InitialScannedAt] [datetime] NULL,
	[ScannedAt] [datetime] NULL,
	[DocumentTypeId] [int] NULL,
	[RecipientId] [int] NULL,
	[RecipientAddress] [varchar](100) NULL,
	[LanguageId] [int] NULL,
	[NotificationStatusId] [int] NULL,
	[ConfidentialityCode] [nvarchar](100) NULL,
	[DirectionId] [int] NULL,
	[DOC_DOKUMENT_ID] [varchar](100) NULL,
	[DocumentOrder] [varchar](100) NULL,
	[DocumentStatusId] [int] NULL,
	[InboundChannelId] [int] NULL,
	[ApplicationNo] [varchar](100) NULL,
	[ApplicationNos] [varchar](100) NULL,
	[PartnerNoSyrius] [varchar](100) NULL,
	[PartnerNoGav] [varchar](100) NULL,
	[PartnerNoGpv] [varchar](100) NULL,
	[PartnerNoRgi] [varchar](100) NULL,
	[ProductCode] [varchar](100) NULL,
	[Remark] [varchar](100) NULL,
	[ScanLocationId] [int] NULL,
	[ScanUser] [varchar](100) NULL,
	[FormNo] [varchar](100) NULL,
	[PersonnelNo] [varchar](100) NULL,
	[PolicyNo] [varchar](100) NULL,
	[PolicyNos] [varchar](100) NULL,
	[ClaimNo] [varchar](100) NULL,
	[ProceedingNo] [varchar](100) NULL,
	[CurrencyId] [int] NULL,
	[AmountText] [varchar](100) NULL,
	[CompanyCode] [varchar](100) NULL,
	[QuantityText] [varchar](100) NULL,
	[BusinessType] [varchar](100) NULL,
	[ContactPerson] [varchar](100) NULL,
	[VendorNo] [varchar](100) NULL,
	[QuoteNo] [varchar](100) NULL,
	[AccountNo] [varchar](100) NULL,
	[Description] [nvarchar](max) NULL,
	[PendingText] [varchar](100) NULL,
	[VoucherDateText] [varchar](100) NULL,
	[FundName] [varchar](100) NULL,
	[ContractNo] [varchar](100) NULL,
	[ContractPartner] [varchar](100) NULL,
	[DossierNo] [varchar](100) NULL,
	[ReferenceNo] [varchar](100) NULL,
	[OriginId] [int] NULL,
	[InterfaceLinkId] [int] NULL,
	[PostCheck1Id] [int] NULL,
	[PostCheck2Id] [int] NULL,
	[ImportedAt] [datetime] NULL,
	[SourceCsvFileName] [nvarchar](100) NULL,
	[Amount]  AS (TRY_CAST(replace(replace(replace(nullif(ltrim(rtrim([AmountText])),''),'''',''),' ',''),',','.') AS [decimal](18,2))),
	[Quantity]  AS (TRY_CAST(replace(nullif(ltrim(rtrim([QuantityText])),''),',','.') AS [decimal](18,3))),
	[VoucherDate]  AS (TRY_CONVERT([date],nullif(ltrim(rtrim([VoucherDateText])),''),(104))),
	[IsPending]  AS (case [PendingText] when 'True' then CONVERT([bit],(1)) when 'False' then CONVERT([bit],(0))  end),
 CONSTRAINT [PK_Documents] PRIMARY KEY CLUSTERED 
(
	[Id] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Documents_ScannedAt] ON [dbo].[Documents]
(
	[ScannedAt] ASC
)
INCLUDE ( 	[InterfaceLinkId],
	[CommunicationTypeId],
	[DocumentTypeId],
	[RecipientId],
	[LanguageId],
	[InboundChannelId],
	[PostCheck1Id],
	[PostCheck2Id]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE UNIQUE NONCLUSTERED INDEX [UQ_Documents_DocumentId] ON [dbo].[Documents]
(
	[DocumentId] ASC
)
WHERE ([DocumentId] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Documents] ADD  CONSTRAINT [DF_Documents_ImportedAt]  DEFAULT (getdate()) FOR [ImportedAt]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_CommunicationTypes] FOREIGN KEY([CommunicationTypeId])
REFERENCES [dbo].[CommunicationTypes] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_CommunicationTypes]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_Currencies] FOREIGN KEY([CurrencyId])
REFERENCES [dbo].[Currencies] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_Currencies]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_Directions] FOREIGN KEY([DirectionId])
REFERENCES [dbo].[Directions] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_Directions]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_DocumentStatuses] FOREIGN KEY([DocumentStatusId])
REFERENCES [dbo].[DocumentStatuses] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_DocumentStatuses]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_DocumentTypes] FOREIGN KEY([DocumentTypeId])
REFERENCES [dbo].[DocumentTypes] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_DocumentTypes]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_InboundChannels] FOREIGN KEY([InboundChannelId])
REFERENCES [dbo].[InboundChannels] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_InboundChannels]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_InterfaceLinks] FOREIGN KEY([InterfaceLinkId])
REFERENCES [dbo].[InterfaceLinks] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_InterfaceLinks]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_Languages] FOREIGN KEY([LanguageId])
REFERENCES [dbo].[Languages] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_Languages]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_NotificationStatuses] FOREIGN KEY([NotificationStatusId])
REFERENCES [dbo].[NotificationStatuses] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_NotificationStatuses]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_Origins] FOREIGN KEY([OriginId])
REFERENCES [dbo].[Origins] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_Origins]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_PostChecks_PostCheck1] FOREIGN KEY([PostCheck1Id])
REFERENCES [dbo].[PostChecks] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_PostChecks_PostCheck1]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_PostChecks_PostCheck2] FOREIGN KEY([PostCheck2Id])
REFERENCES [dbo].[PostChecks] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_PostChecks_PostCheck2]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_Recipients] FOREIGN KEY([RecipientId])
REFERENCES [dbo].[Recipients] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_Recipients]
GO
ALTER TABLE [dbo].[Documents]  WITH CHECK ADD  CONSTRAINT [FK_Documents_ScanLocations] FOREIGN KEY([ScanLocationId])
REFERENCES [dbo].[ScanLocations] ([Id])
GO
ALTER TABLE [dbo].[Documents] CHECK CONSTRAINT [FK_Documents_ScanLocations]
GO
