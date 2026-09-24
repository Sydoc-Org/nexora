-- 0129_generali_documents_renamed_fields.sql
-- Issue #220, phase 3, NexoraDB side. GeneraliDB 0007 renamed dbo.ReportJob to
-- dbo.Documents and 61 of its columns, and added dbo.v_Documents -- the same
-- read view under English output names.
--
-- The reporting registry stores object *and field* names as data, so it has to
-- follow. Three places:
--
--   ReportingSources.BaseObject   generali_documents -> dbo.v_Documents
--   ReportingSources.ColumnsJSON  the 22 catalogued DOC_* fields
--   ReportingMetrics              BaseField 'CASE_ID' and the FilterJson on
--                                 DOC_NK1/DOC_NK2 behind "Documents without
--                                 post-check"
--   Reports.DefinitionJSON        saved user reports built on generali_documents
--
-- Saved reports are rewritten rather than left to break. INT has none, but this
-- source has existed on PROD since 0119 and somebody may have saved one in the
-- meantime; a report whose columns silently stop resolving is a worse outcome
-- than a string rewrite. The rewrite is a chain of REPLACE over the *quoted*
-- field tokens ('"DOC_SCANDATUM"' -> '"ScannedAt"'), scoped to rows that name
-- the generali_documents source, so a filter *value* that happened to equal a
-- field name is the only way it could overreach -- and none exists.
--
-- ReportingAiAudit / ReportingSqlAudit are deliberately untouched: they record
-- the SQL that actually ran at the time.
--
-- Not moved here: dbo.v_ReportJobJoinDefinitions still exists as a compat view
-- over v_Documents with the old column names, so anything this migration
-- misses keeps working until phase 6 drops it.
--
-- Idempotent -- every statement is a no-op once the tokens are gone.

UPDATE dbo.ReportingSources SET BaseObject = 'dbo.v_Documents'
WHERE Code = 'generali_documents' AND BaseObject = 'dbo.v_ReportJobJoinDefinitions';
GO

UPDATE dbo.ReportingSources
SET ColumnsJSON =
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(ColumnsJSON,
        '"CASE_FOLDERNAME"', '"ScanCaseFolderName"'),
        '"CASE_ID"', '"ScanCaseId"'),
        '"DOC_ANTRAG_NR"', '"ApplicationNo"'),
        '"DOC_ANTRAG_NR_MULTI"', '"ApplicationNos"'),
        '"DOC_ANZAHL"', '"QuantityText"'),
        '"DOC_BELEGDATUM"', '"VoucherDateText"'),
        '"DOC_BEMERKUNG"', '"Remark"'),
        '"DOC_BETRAG"', '"AmountText"'),
        '"DOC_BEZEICHNUNG"', '"Description"'),
        '"DOC_BUCHUNGSKREIS_NR"', '"CompanyCode"'),
        '"DOC_CASE_ID"', '"CaseId"'),
        '"DOC_COUVERTDOCCOUNT"', '"EnvelopeDocumentCount"'),
        '"DOC_COUVERT_ID"', '"EnvelopeId"'),
        '"DOC_DOKUMENTENORDER"', '"DocumentOrder"'),
        '"DOC_DOKUMENTENSTATUS"', '"DocumentStatus"'),
        '"DOC_DOKUMENTENTYP"', '"DocumentType"'),
        '"DOC_DOSSIER_NR"', '"DossierNo"'),
        '"DOC_DateCreated"', '"CreatedAt"'),
        '"DOC_EINGANGSKANAL"', '"InboundChannel"'),
        '"DOC_EMPFAENGER"', '"Recipient"'),
        '"DOC_EMPFAENGERADRESSE"', '"RecipientAddress"'),
        '"DOC_FONDSNAME"', '"FundName"'),
        '"DOC_FORMULAR_NR"', '"FormNo"'),
        '"DOC_GESCHAEFTSART"', '"BusinessType"'),
        '"DOC_ID"', '"DocumentId"'),
        '"DOC_INITIAL_USER"', '"InitialUser"'),
        '"DOC_INTERFACE_LINK"', '"InterfaceLink"'),
        '"DOC_KOMMUNIKATION"', '"CommunicationType"'),
        '"DOC_KONTAKTPERSON"', '"ContactPerson"'),
        '"DOC_KONTONUMMER"', '"AccountNo"'),
        '"DOC_KREDITOREN_NR"', '"VendorNo"'),
        '"DOC_NK1"', '"PostCheck1"'),
        '"DOC_NK2"', '"PostCheck2"'),
        '"DOC_NOTIFIKATIONSSTATUS"', '"NotificationStatus"'),
        '"DOC_OFFERTEN_NR"', '"QuoteNo"'),
        '"DOC_ORIGIN"', '"Origin"'),
        '"DOC_PARTNER_NR_GAV"', '"PartnerNoGav"'),
        '"DOC_PARTNER_NR_GPV"', '"PartnerNoGpv"'),
        '"DOC_PARTNER_NR_RGI"', '"PartnerNoRgi"'),
        '"DOC_PARTNER_NR_SYRIUS"', '"PartnerNoSyrius"'),
        '"DOC_PENDING"', '"PendingText"'),
        '"DOC_PERSONAL_NR"', '"PersonnelNo"'),
        '"DOC_POLICEN_NR"', '"PolicyNo"'),
        '"DOC_POLICEN_NR_MULTI"', '"PolicyNos"'),
        '"DOC_PRODUKT_CODE"', '"ProductCode"'),
        '"DOC_REFERENZNUMMER"', '"ReferenceNo"'),
        '"DOC_RICHTUNG"', '"Direction"'),
        '"DOC_SCANDATUM"', '"ScannedAt"'),
        '"DOC_SCANDATUM_INITIAL"', '"InitialScannedAt"'),
        '"DOC_SCANORT"', '"ScanLocation"'),
        '"DOC_SCANUSER"', '"ScanUser"'),
        '"DOC_SCHADEN_NR"', '"ClaimNo"'),
        '"DOC_SPRACHE"', '"Language"'),
        '"DOC_VERFAHREN_NR"', '"ProceedingNo"'),
        '"DOC_VERTRAGSNUMMER"', '"ContractNo"'),
        '"DOC_VERTRAGSPARTNER"', '"ContractPartner"'),
        '"DOC_VERTRAULICHKEIT"', '"ConfidentialityCode"'),
        '"DOC_WAEHRUNG"', '"Currency"'),
        '"SourceCSVFileName"', '"SourceCsvFileName"')
WHERE Code = 'generali_documents';
GO

UPDATE dbo.ReportingMetrics SET BaseField = 'ScanCaseId'
WHERE SourceId = 'generali_documents' AND BaseField = 'CASE_ID';

UPDATE dbo.ReportingMetrics
SET FilterJson =
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(FilterJson,
        '"CASE_FOLDERNAME"', '"ScanCaseFolderName"'),
        '"CASE_ID"', '"ScanCaseId"'),
        '"DOC_ANTRAG_NR"', '"ApplicationNo"'),
        '"DOC_ANTRAG_NR_MULTI"', '"ApplicationNos"'),
        '"DOC_ANZAHL"', '"QuantityText"'),
        '"DOC_BELEGDATUM"', '"VoucherDateText"'),
        '"DOC_BEMERKUNG"', '"Remark"'),
        '"DOC_BETRAG"', '"AmountText"'),
        '"DOC_BEZEICHNUNG"', '"Description"'),
        '"DOC_BUCHUNGSKREIS_NR"', '"CompanyCode"'),
        '"DOC_CASE_ID"', '"CaseId"'),
        '"DOC_COUVERTDOCCOUNT"', '"EnvelopeDocumentCount"'),
        '"DOC_COUVERT_ID"', '"EnvelopeId"'),
        '"DOC_DOKUMENTENORDER"', '"DocumentOrder"'),
        '"DOC_DOKUMENTENSTATUS"', '"DocumentStatus"'),
        '"DOC_DOKUMENTENTYP"', '"DocumentType"'),
        '"DOC_DOSSIER_NR"', '"DossierNo"'),
        '"DOC_DateCreated"', '"CreatedAt"'),
        '"DOC_EINGANGSKANAL"', '"InboundChannel"'),
        '"DOC_EMPFAENGER"', '"Recipient"'),
        '"DOC_EMPFAENGERADRESSE"', '"RecipientAddress"'),
        '"DOC_FONDSNAME"', '"FundName"'),
        '"DOC_FORMULAR_NR"', '"FormNo"'),
        '"DOC_GESCHAEFTSART"', '"BusinessType"'),
        '"DOC_ID"', '"DocumentId"'),
        '"DOC_INITIAL_USER"', '"InitialUser"'),
        '"DOC_INTERFACE_LINK"', '"InterfaceLink"'),
        '"DOC_KOMMUNIKATION"', '"CommunicationType"'),
        '"DOC_KONTAKTPERSON"', '"ContactPerson"'),
        '"DOC_KONTONUMMER"', '"AccountNo"'),
        '"DOC_KREDITOREN_NR"', '"VendorNo"'),
        '"DOC_NK1"', '"PostCheck1"'),
        '"DOC_NK2"', '"PostCheck2"'),
        '"DOC_NOTIFIKATIONSSTATUS"', '"NotificationStatus"'),
        '"DOC_OFFERTEN_NR"', '"QuoteNo"'),
        '"DOC_ORIGIN"', '"Origin"'),
        '"DOC_PARTNER_NR_GAV"', '"PartnerNoGav"'),
        '"DOC_PARTNER_NR_GPV"', '"PartnerNoGpv"'),
        '"DOC_PARTNER_NR_RGI"', '"PartnerNoRgi"'),
        '"DOC_PARTNER_NR_SYRIUS"', '"PartnerNoSyrius"'),
        '"DOC_PENDING"', '"PendingText"'),
        '"DOC_PERSONAL_NR"', '"PersonnelNo"'),
        '"DOC_POLICEN_NR"', '"PolicyNo"'),
        '"DOC_POLICEN_NR_MULTI"', '"PolicyNos"'),
        '"DOC_PRODUKT_CODE"', '"ProductCode"'),
        '"DOC_REFERENZNUMMER"', '"ReferenceNo"'),
        '"DOC_RICHTUNG"', '"Direction"'),
        '"DOC_SCANDATUM"', '"ScannedAt"'),
        '"DOC_SCANDATUM_INITIAL"', '"InitialScannedAt"'),
        '"DOC_SCANORT"', '"ScanLocation"'),
        '"DOC_SCANUSER"', '"ScanUser"'),
        '"DOC_SCHADEN_NR"', '"ClaimNo"'),
        '"DOC_SPRACHE"', '"Language"'),
        '"DOC_VERFAHREN_NR"', '"ProceedingNo"'),
        '"DOC_VERTRAGSNUMMER"', '"ContractNo"'),
        '"DOC_VERTRAGSPARTNER"', '"ContractPartner"'),
        '"DOC_VERTRAULICHKEIT"', '"ConfidentialityCode"'),
        '"DOC_WAEHRUNG"', '"Currency"'),
        '"SourceCSVFileName"', '"SourceCsvFileName"')
WHERE SourceId = 'generali_documents' AND FilterJson IS NOT NULL;

UPDATE dbo.ReportingMetrics
SET Description = REPLACE(Description, 'ReportJob rows', 'Documents rows')
WHERE Description LIKE '%ReportJob rows%';
GO

-- Saved report definitions on this source, if any exist.
UPDATE dbo.Reports
SET DefinitionJSON =
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(DefinitionJSON,
        '"CASE_FOLDERNAME"', '"ScanCaseFolderName"'),
        '"CASE_ID"', '"ScanCaseId"'),
        '"DOC_ANTRAG_NR"', '"ApplicationNo"'),
        '"DOC_ANTRAG_NR_MULTI"', '"ApplicationNos"'),
        '"DOC_ANZAHL"', '"QuantityText"'),
        '"DOC_BELEGDATUM"', '"VoucherDateText"'),
        '"DOC_BEMERKUNG"', '"Remark"'),
        '"DOC_BETRAG"', '"AmountText"'),
        '"DOC_BEZEICHNUNG"', '"Description"'),
        '"DOC_BUCHUNGSKREIS_NR"', '"CompanyCode"'),
        '"DOC_CASE_ID"', '"CaseId"'),
        '"DOC_COUVERTDOCCOUNT"', '"EnvelopeDocumentCount"'),
        '"DOC_COUVERT_ID"', '"EnvelopeId"'),
        '"DOC_DOKUMENTENORDER"', '"DocumentOrder"'),
        '"DOC_DOKUMENTENSTATUS"', '"DocumentStatus"'),
        '"DOC_DOKUMENTENTYP"', '"DocumentType"'),
        '"DOC_DOSSIER_NR"', '"DossierNo"'),
        '"DOC_DateCreated"', '"CreatedAt"'),
        '"DOC_EINGANGSKANAL"', '"InboundChannel"'),
        '"DOC_EMPFAENGER"', '"Recipient"'),
        '"DOC_EMPFAENGERADRESSE"', '"RecipientAddress"'),
        '"DOC_FONDSNAME"', '"FundName"'),
        '"DOC_FORMULAR_NR"', '"FormNo"'),
        '"DOC_GESCHAEFTSART"', '"BusinessType"'),
        '"DOC_ID"', '"DocumentId"'),
        '"DOC_INITIAL_USER"', '"InitialUser"'),
        '"DOC_INTERFACE_LINK"', '"InterfaceLink"'),
        '"DOC_KOMMUNIKATION"', '"CommunicationType"'),
        '"DOC_KONTAKTPERSON"', '"ContactPerson"'),
        '"DOC_KONTONUMMER"', '"AccountNo"'),
        '"DOC_KREDITOREN_NR"', '"VendorNo"'),
        '"DOC_NK1"', '"PostCheck1"'),
        '"DOC_NK2"', '"PostCheck2"'),
        '"DOC_NOTIFIKATIONSSTATUS"', '"NotificationStatus"'),
        '"DOC_OFFERTEN_NR"', '"QuoteNo"'),
        '"DOC_ORIGIN"', '"Origin"'),
        '"DOC_PARTNER_NR_GAV"', '"PartnerNoGav"'),
        '"DOC_PARTNER_NR_GPV"', '"PartnerNoGpv"'),
        '"DOC_PARTNER_NR_RGI"', '"PartnerNoRgi"'),
        '"DOC_PARTNER_NR_SYRIUS"', '"PartnerNoSyrius"'),
        '"DOC_PENDING"', '"PendingText"'),
        '"DOC_PERSONAL_NR"', '"PersonnelNo"'),
        '"DOC_POLICEN_NR"', '"PolicyNo"'),
        '"DOC_POLICEN_NR_MULTI"', '"PolicyNos"'),
        '"DOC_PRODUKT_CODE"', '"ProductCode"'),
        '"DOC_REFERENZNUMMER"', '"ReferenceNo"'),
        '"DOC_RICHTUNG"', '"Direction"'),
        '"DOC_SCANDATUM"', '"ScannedAt"'),
        '"DOC_SCANDATUM_INITIAL"', '"InitialScannedAt"'),
        '"DOC_SCANORT"', '"ScanLocation"'),
        '"DOC_SCANUSER"', '"ScanUser"'),
        '"DOC_SCHADEN_NR"', '"ClaimNo"'),
        '"DOC_SPRACHE"', '"Language"'),
        '"DOC_VERFAHREN_NR"', '"ProceedingNo"'),
        '"DOC_VERTRAGSNUMMER"', '"ContractNo"'),
        '"DOC_VERTRAGSPARTNER"', '"ContractPartner"'),
        '"DOC_VERTRAULICHKEIT"', '"ConfidentialityCode"'),
        '"DOC_WAEHRUNG"', '"Currency"'),
        '"SourceCSVFileName"', '"SourceCsvFileName"')
WHERE DefinitionJSON LIKE '%"generali_documents"%';
GO
