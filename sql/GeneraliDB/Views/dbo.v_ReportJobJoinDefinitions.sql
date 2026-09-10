USE [Generali]
GO
DROP VIEW [dbo].[v_ReportJobJoinDefinitions]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO

-- ---------------------------------------------------------------------------
-- 3. Rebuild v_ReportJobJoinDefinitions on the new lookup names.
--    Output columns are byte-for-byte the ones it exposed before, so no
--    application code changes because of this view. Phase 3 renames the view
--    itself to v_Documents and renames these output columns with it.
--    Note the WHERE: this view has always shown only the CaptivaCapture rows
--    (890,298 of 2,682,707 on INT), which is easy to miss.
-- ---------------------------------------------------------------------------
CREATE   VIEW [dbo].[v_ReportJobJoinDefinitions]
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
