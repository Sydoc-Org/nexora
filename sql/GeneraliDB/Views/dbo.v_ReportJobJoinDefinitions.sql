USE [Generali]
GO
DROP VIEW [dbo].[v_ReportJobJoinDefinitions]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO




CREATE VIEW [dbo].[v_ReportJobJoinDefinitions]
as 
SELECT
      [CASE_ID]
      ,[CASE_FOLDERNAME]
      ,[DOC_ID]
      ,[DOC_COUVERT_ID]
      ,[DOC_CASE_ID]
      ,[DOC_JOURNAL_ID]
      ,[DOC_DateCreated]
      ,[DOC_COUVERTDOCCOUNT]
      ,k.value DOC_KOMMUNIKATION
      ,[DOC_INITIAL_USER]
      ,[DOC_SCANDATUM_INITIAL]
      ,[DOC_SCANDATUM]
      ,dt.Value DOC_DOKUMENTENTYP
      ,e.Value DOC_EMPFAENGER
      ,[DOC_EMPFAENGERADRESSE]
      ,spr.Value DOC_SPRACHE
      ,n.Value DOC_NOTIFIKATIONSSTATUS
      ,[DOC_VERTRAULICHKEIT]
      ,r.Value DOC_RICHTUNG
      ,[DOC_DOKUMENT_ID]
      ,[DOC_DOKUMENTENORDER]
      ,ds.Value DOC_DOKUMENTENSTATUS
      ,[DOC_DOKUMENT_URL]
      ,ek.Value DOC_EINGANGSKANAL
      ,[DOC_ANTRAG_NR]
      ,[DOC_ANTRAG_NR_MULTI]
      ,[DOC_PARTNER_NR_SYRIUS]
      ,[DOC_PARTNER_NR_GAV]
      ,[DOC_PARTNER_NR_GPV]
      ,[DOC_PARTNER_NR_RGI]
      ,[DOC_PRODUKT_CODE]
      ,[DOC_BEMERKUNG]
      ,so.value DOC_SCANORT
      ,[DOC_SCANUSER]
      ,[DOC_FORMULAR_NR]
      ,[DOC_PERSONAL_NR]
      ,[DOC_POLICEN_NR]
      ,[DOC_POLICEN_NR_MULTI]
      ,[DOC_SCHADEN_NR]
      ,[DOC_VERFAHREN_NR]
      ,w.value DOC_WAEHRUNG
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
      ,u.value DOC_ORIGIN
      ,ifl.Value DOC_INTERFACE_LINK
      ,nk1.value DOC_NK1
      ,nk2.value DOC_NK2
      ,SourceCSVFileName
  FROM [Generali].[dbo].[ReportJob] rj
  LEFT JOIN DokumentenStatus ds on ds.id = rj.DOC_DOKUMENTENSTATUS
  LEFT JOIN DokumentenTyp dt on dt.id = rj.DOC_DOKUMENTENTYP
  LEFT JOIN Eingangskanal ek on ek.id = rj.DOC_EINGANGSKANAL
  LEFT JOIN Empfaenger e on e.id = rj.DOC_EMPFAENGER
  LEFT JOIN InterfaceLink ifl on ifl.id = rj.DOC_INTERFACE_LINK
  LEFT JOIN Kommunikation k on k.id = rj.DOC_KOMMUNIKATION
  LEFT JOIN Nachkontrolle nk1 on nk1.id = rj.DOC_NK1
  LEFT JOIN Nachkontrolle nk2 on nk2.id = rj.DOC_NK2
LEFT JOIN Notifikationsstatus n on n.id = rj.DOC_NOTIFIKATIONSSTATUS
LEFT JOIN Richtung r on r.id = rj.DOC_RICHTUNG
LEFT JOIN Scanort so on so.id = rj.DOC_SCANORT
LEFT JOIN Sprache spr on spr.id = rj.DOC_SPRACHE
LEFT JOIN Ursprung u on u.id = rj.DOC_ORIGIN
LEFT JOIN Waehrung w on w.id = rj.DOC_WAEHRUNG 
WHERE ifl.Value = 'CaptivaCapture'
GO
