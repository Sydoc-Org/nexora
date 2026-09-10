USE [Generali]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Waehrung]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Ursprung]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Sprache]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_ScanOrt]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Richtung]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_NotifikationsStatus]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Nachkontrolle_NK2]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Nachkontrolle_NK1]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Kommunikation]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_InterfaceLink]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Empfaenger]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_Eingangskanal]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_DokumentenTyp]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [FK_ReportJob_DokumentenStatus]
GO
ALTER TABLE [dbo].[ReportJob] DROP CONSTRAINT [DF_ReportJob_InsertedAt]
GO
DROP INDEX [UQ_ReportJob_DOC_ID] ON [dbo].[ReportJob]
GO
DROP INDEX [IX_ReportJob_DOC_SCANDATUM] ON [dbo].[ReportJob]
GO
DROP TABLE [dbo].[ReportJob]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportJob](
	[RecordID] [int] IDENTITY(1,1) NOT NULL,
	[CASE_ID] [varchar](100) NULL,
	[CASE_FOLDERNAME] [varchar](100) NULL,
	[DOC_ID] [varchar](100) NULL,
	[DOC_COUVERT_ID] [varchar](100) NULL,
	[DOC_CASE_ID] [varchar](100) NULL,
	[DOC_JOURNAL_ID] [varchar](100) NULL,
	[DOC_DateCreated] [datetime] NULL,
	[DOC_COUVERTDOCCOUNT] [int] NULL,
	[DOC_KOMMUNIKATION] [int] NULL,
	[DOC_INITIAL_USER] [varchar](100) NULL,
	[DOC_SCANDATUM_INITIAL] [datetime] NULL,
	[DOC_SCANDATUM] [datetime] NULL,
	[DOC_DOKUMENTENTYP] [int] NULL,
	[DOC_EMPFAENGER] [int] NULL,
	[DOC_EMPFAENGERADRESSE] [varchar](100) NULL,
	[DOC_SPRACHE] [int] NULL,
	[DOC_NOTIFIKATIONSSTATUS] [int] NULL,
	[DOC_VERTRAULICHKEIT] [nvarchar](100) NULL,
	[DOC_RICHTUNG] [int] NULL,
	[DOC_DOKUMENT_ID] [varchar](100) NULL,
	[DOC_DOKUMENTENORDER] [varchar](100) NULL,
	[DOC_DOKUMENTENSTATUS] [int] NULL,
	[DOC_DOKUMENT_URL] [varchar](100) NULL,
	[DOC_EINGANGSKANAL] [int] NULL,
	[DOC_ANTRAG_NR] [varchar](100) NULL,
	[DOC_ANTRAG_NR_MULTI] [varchar](100) NULL,
	[DOC_PARTNER_NR_SYRIUS] [varchar](100) NULL,
	[DOC_PARTNER_NR_GAV] [varchar](100) NULL,
	[DOC_PARTNER_NR_GPV] [varchar](100) NULL,
	[DOC_PARTNER_NR_RGI] [varchar](100) NULL,
	[DOC_PRODUKT_CODE] [varchar](100) NULL,
	[DOC_BEMERKUNG] [varchar](100) NULL,
	[DOC_SCANORT] [int] NULL,
	[DOC_SCANUSER] [varchar](100) NULL,
	[DOC_FORMULAR_NR] [varchar](100) NULL,
	[DOC_PERSONAL_NR] [varchar](100) NULL,
	[DOC_POLICEN_NR] [varchar](100) NULL,
	[DOC_POLICEN_NR_MULTI] [varchar](100) NULL,
	[DOC_SCHADEN_NR] [varchar](100) NULL,
	[DOC_VERFAHREN_NR] [varchar](100) NULL,
	[DOC_WAEHRUNG] [int] NULL,
	[DOC_BETRAG] [varchar](100) NULL,
	[DOC_BUCHUNGSKREIS_NR] [varchar](100) NULL,
	[DOC_ANZAHL] [varchar](100) NULL,
	[DOC_GESCHAEFTSART] [varchar](100) NULL,
	[DOC_KONTAKTPERSON] [varchar](100) NULL,
	[DOC_KREDITOREN_NR] [varchar](100) NULL,
	[DOC_OFFERTEN_NR] [varchar](100) NULL,
	[DOC_KONTONUMMER] [varchar](100) NULL,
	[DOC_BEZEICHNUNG] [nvarchar](max) NULL,
	[DOC_PENDING] [varchar](100) NULL,
	[DOC_ALFdpages] [varchar](100) NULL,
	[DOC_ALFpages] [varchar](100) NULL,
	[DOC_PageSize] [varchar](100) NULL,
	[DOC_SAPCompCharset] [varchar](100) NULL,
	[DOC_SAPCompCreated] [varchar](100) NULL,
	[DOC_SAPCompModified] [varchar](100) NULL,
	[DOC_SAPComps] [varchar](100) NULL,
	[DOC_SAPCompSize] [varchar](100) NULL,
	[DOC_SAPCompVersion] [varchar](100) NULL,
	[DOC_SAPContType] [varchar](100) NULL,
	[DOC_SAPDocDate] [varchar](100) NULL,
	[DOC_SAPDocId] [varchar](100) NULL,
	[DOC_SAPDocProt] [varchar](100) NULL,
	[DOC_SAPType] [varchar](100) NULL,
	[DOC_BARCODENR] [varchar](100) NULL,
	[DOC_BELEGDATUM] [varchar](100) NULL,
	[DOC_FONDSNAME] [varchar](100) NULL,
	[DOC_VERTRAGSNUMMER] [varchar](100) NULL,
	[DOC_VERTRAGSPARTNER] [varchar](100) NULL,
	[DOC_DOSSIER_NR] [varchar](100) NULL,
	[DOC_REFERENZNUMMER] [varchar](100) NULL,
	[DOC_ORIGIN] [int] NULL,
	[DOC_INTERFACE_LINK] [int] NULL,
	[DOC_NK1] [int] NULL,
	[DOC_NK2] [int] NULL,
	[InsertedAt] [datetime] NULL,
	[SourceCSVFileName] [nvarchar](100) NULL,
 CONSTRAINT [PK_ReportJob] PRIMARY KEY CLUSTERED 
(
	[RecordID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ReportJob_DOC_SCANDATUM] ON [dbo].[ReportJob]
(
	[DOC_SCANDATUM] ASC
)
INCLUDE ( 	[DOC_INTERFACE_LINK],
	[DOC_KOMMUNIKATION],
	[DOC_DOKUMENTENTYP],
	[DOC_EMPFAENGER],
	[DOC_SPRACHE],
	[DOC_EINGANGSKANAL],
	[DOC_NK1],
	[DOC_NK2]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE UNIQUE NONCLUSTERED INDEX [UQ_ReportJob_DOC_ID] ON [dbo].[ReportJob]
(
	[DOC_ID] ASC
)
WHERE ([DOC_ID] IS NOT NULL)
WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, IGNORE_DUP_KEY = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportJob] ADD  CONSTRAINT [DF_ReportJob_InsertedAt]  DEFAULT (getdate()) FOR [InsertedAt]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_DokumentenStatus] FOREIGN KEY([DOC_DOKUMENTENSTATUS])
REFERENCES [dbo].[DokumentenStatus] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_DokumentenStatus]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_DokumentenTyp] FOREIGN KEY([DOC_DOKUMENTENTYP])
REFERENCES [dbo].[DokumentenTyp] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_DokumentenTyp]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Eingangskanal] FOREIGN KEY([DOC_EINGANGSKANAL])
REFERENCES [dbo].[Eingangskanal] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Eingangskanal]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Empfaenger] FOREIGN KEY([DOC_EMPFAENGER])
REFERENCES [dbo].[Empfaenger] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Empfaenger]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_InterfaceLink] FOREIGN KEY([DOC_INTERFACE_LINK])
REFERENCES [dbo].[InterfaceLink] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_InterfaceLink]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Kommunikation] FOREIGN KEY([DOC_KOMMUNIKATION])
REFERENCES [dbo].[Kommunikation] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Kommunikation]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Nachkontrolle_NK1] FOREIGN KEY([DOC_NK1])
REFERENCES [dbo].[Nachkontrolle] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Nachkontrolle_NK1]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Nachkontrolle_NK2] FOREIGN KEY([DOC_NK2])
REFERENCES [dbo].[Nachkontrolle] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Nachkontrolle_NK2]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_NotifikationsStatus] FOREIGN KEY([DOC_NOTIFIKATIONSSTATUS])
REFERENCES [dbo].[NotifikationsStatus] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_NotifikationsStatus]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Richtung] FOREIGN KEY([DOC_RICHTUNG])
REFERENCES [dbo].[Richtung] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Richtung]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_ScanOrt] FOREIGN KEY([DOC_SCANORT])
REFERENCES [dbo].[ScanOrt] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_ScanOrt]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Sprache] FOREIGN KEY([DOC_SPRACHE])
REFERENCES [dbo].[Sprache] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Sprache]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Ursprung] FOREIGN KEY([DOC_ORIGIN])
REFERENCES [dbo].[Ursprung] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Ursprung]
GO
ALTER TABLE [dbo].[ReportJob]  WITH CHECK ADD  CONSTRAINT [FK_ReportJob_Waehrung] FOREIGN KEY([DOC_WAEHRUNG])
REFERENCES [dbo].[Waehrung] ([ID])
GO
ALTER TABLE [dbo].[ReportJob] CHECK CONSTRAINT [FK_ReportJob_Waehrung]
GO
