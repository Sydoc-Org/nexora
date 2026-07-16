# Standardised Statistics DB schema

Design proposal for replacing the grown per-client tables in `sydoc_stat` with one
fixed schema. DDL: [`standard-schema.sql`](standard-schema.sql). Derived from the
live INT/PRD statistics DB (37 tables dumped 2026-07-16; backup copies `*_old`,
`*_2018_2021`, dated snapshots excluded).

## Design in one paragraph

One core fact table `dbo.Documents` (one row per processed document, fixed
lifecycle columns), a typed 1:1 satellite `dbo.InvoiceDetails` for the dominant
process type, `dbo.ValidationSteps` for multi-pass validation, `dbo.DocumentValues`
(extracted vs. final, one row per field) for everything client-specific, and
`dbo.FieldValidationEvents` as the merged, typed successor of the seven identical
`*_Collect_Field_Attributes` tables. Side domains get their own small tables:
`DocumentExports`, `TransferEvents`, `DailyVolumes`, `LicenseUsage`, `TimeEntries`.
`dbo.Clients` + `dbo.Processes` replace the routing role of `NexoraDB.dbo.Statconfig`.

## Naming & type rules

| Rule | Standard | Replaces |
|---|---|---|
| Tables | `dbo.` + PascalCase plural (`Documents`) | `EM_Invoice`, `PriveraPosteingang`, `SFTP_Statistik`, ... |
| Columns | PascalCase, English, no suffixes/prefixes | `ImportDatetime_dt`, `WorkitemID_bi`, `AnzImagesIn`, `NS_ScanDatum` |
| PK / FK | `<TableSingular>Id`, FK keeps referenced name | `SQL_ID`, `LID`, `SBID`, `S2MID`, `DBUID` |
| Timestamps | `<Verb>edAt datetime2(0)` | dates in `nvarchar(50)`, `datetime`, `datetime2`, `text` |
| Pure dates | `<Noun>Date date` | `Datum`, `DocDate`, `EndDocDate` |
| Users | `<Verb>edBy nvarchar(50)` | `ValUser`, `DeleteByUser`, `Benutzer`, `DemandedBy` |
| Flags | `Is<X>` / `Has<X>` `bit` | `nvarchar(5)` 'true'/'false', `nchar(10)`, `int` 0/1 |
| Money | `decimal(18,2)` + `CurrencyCode char(3)` | `GrossAmount nvarchar(50)`, `DocCurrency nvarchar(4/50)` |
| Counts | `<X>Count int` | `Anz*`, `Seiten`, `Pages`, `Doc_Pages nvarchar(10)` |

MS02 Postgres mirror: identical names, double-quoted PascalCase
(`public."Documents"`), `timestamptz` for `datetime2`, `boolean` for `bit`.

## Table mapping (old → new)

| Source table | New home |
|---|---|
| `BFH_Statistic` | `Documents` + `InvoiceDetails` + `ValidationSteps` (Val/Admin/Approved passes) + `DocumentValues` (WorkflowStamp, Zuordnung, TopId, ROOTING, ...) |
| `Bucherer_Invoice`, `Compass_Invoice`, `EM_Invoice`, `PriveraInvoice`, `Migrolino_AG`, `Migrolino_Franchise` | `Documents` + `InvoiceDetails` + `ValidationSteps`; client oddballs → `DocumentValues` |
| `PriveraInvoice` `extractedX`/`X` pairs | `DocumentValues.ExtractedValue` / `.FinalValue`, `FieldCode = X` |
| `PriveraPosteingang` | `Documents` + `ValidationSteps`; property-mgmt fields (`EigentuemerNr`, `LiegenschaftsNr`, `MietverhaeltnisNr`, `Empfaenger`, `Vertraulichkeit`, `Einschreiben`, `Nachsendung`, `NS_*`) → `DocumentValues` |
| `PriveraInitialUndNeuzugaenge` | `Documents`; archive fields (`ArchivBoxNummer`, `Langzeitlage`, `obligatorische_physische_archivierung`) → `DocumentValues` |
| `Geberit_Garantiekarten` | `Documents` + `ValidationSteps` |
| `Bucherer_EasyTax` | `Documents` (`FileName`/`DocumentExports` for remote/export file names) |
| `ELSYMailroom` | `Documents` (email columns) + `DocumentExports` (AWS leg, REST leg) |
| `SimpleProcess` | `Documents` + `DocumentValues` (`ContractNumber`, `AgencyName`) |
| all 7 `*_Collect_Field_Attributes` | `FieldValidationEvents` (identical 27-col structures, merged; `ORGANIZATION`/`UNIT`/`PROCESS` → `Processes`) |
| `Bucherer_SFTP_Statistik`, `StadtBiel` | `TransferEvents` |
| `Bucherer_Scan2Mail`, `Frigemo_Scan2Mail` | `DailyVolumes` |
| `DPSLicenseCounter` | `LicenseUsage` |
| `TimeTool` | `TimeEntries` |

## Column synonym dictionary

Every spelling found in the source tables, and where it lands:

| Standard column | Source spellings |
|---|---|
| `Documents.WorkitemId` | `WorkItemID`, `WorkItem`, `Workitem`, `WorkitemID`, `WID`, `WORKITEM_ID`, `WorkitemID_bi`, `WidIndex` |
| `Documents.ParentWorkitemId` | `WorkItemSendung` |
| `Documents.Barcode` | `Barcode`, `DocBarcode`, `BC_Rueckweisung` (rejection → `ValidationSteps.Outcome`) |
| `Documents.ShipmentBarcode` | `Sendungsbarcode` |
| `Documents.ImportedAt` | `ImportDate`, `ImportTime`, `ImportDatetime`, `ImportDatetime_dt` |
| `Documents.ExportedAt` | `ExportDate`, `Export`, `ExportDatetime(_dt)`, `ExportEM(_dt)`, `ExportTime`, `UploadDatetime` |
| `Documents.ScannedAt` | `ScanTime`, `ScanDate`, `ScanDatetime`, `DocScanDate` |
| `Documents.ScannedBy` | `ScanUser`, `DocScanUser` |
| `Documents.DeletedAt` | `GeloeschtAm`, `DokumentGeloeschtAm`, `DeleteInVal` |
| `Documents.DeletedBy` | `DeleteByUser` |
| `Documents.OriginalDestroyedOn/By` | `OrigDestroyed`, `OrigDestroyedByUser`, `DestroyedByUser` |
| `Documents.PageCountScanned` | `AnzImages`, `AnzImagesIn`, `AnzImagesScanned`, `AnzahlImagesScanned`, `Seiten`, `Pages`, `PageCount`, `Doc_Pages` |
| `Documents.PageCountProcessed` | `AnzImagesOut`, `AnzahlImagesProcessed` |
| `Documents.DocumentCount` | `DocCount`, `DocumentCount`, `Dokumente` |
| `Documents.DocumentDate` | `DocDate`, `DokDatum` (`ExtractedDokDatum` → `DocumentValues`) |
| `Documents.DocumentType` | `DocType`, `Dokumenttyp` |
| `Documents.Channel` | `Eingang`, `DocSource`, `ScanSource`, `Art` |
| `Documents.FileName` | `FileName`, `DocFilename`, `FilenamePDF`, `PDF_Name`, `SFTP_Filename` |
| `Documents.EmailMessageId` | `MailID`, `E_Mail_BatchID` |
| `Documents.EmailFrom` | `MailFrom`, `E_Mail_Sender` |
| `Documents.EmailTo` | `MailTo` |
| `Documents.EmailSubject` | `MailSubject` |
| `Documents.AttachmentCount` | `MailAttachmentsNumber` (`MailAttachmentNames` → `DocumentValues`) |
| `Documents.IsDuplicate` | `IsDocDuplicate`, `IsDocDuplicate2`, `Doc_Duplicate` |
| `Documents.DuplicateCode` | `DuplicateCode`, `DocDuplicateCheck` |
| `Documents.IsApproved` | `DocumentApproved`, `DocApproved`, `Approved` |
| `Documents.NoExportReason` | `Reason_no_Export` |
| `Documents.Environment` | `Environment` |
| `ValidationSteps` (rows) | `ValUser(A/B/C)`, `ValUserAdmin`, `ValUserApproved`, `ValTimeSek(A/B/C/Admin/Approved)`, `ValDate`, `UserValidationTime`, `TageZurueckgestellt` (→ `Outcome='deferred'`), `Rueckweisung` (→ `'rejected'`) |
| `InvoiceDetails.InvoiceNumber` | `InvoiceNR`, `DocNo` |
| `InvoiceDetails.Gross/Net/VatAmount` | `GrossAmount`, `NetAmount`, `VatAmount` (all `nvarchar(50)` today) |
| `InvoiceDetails.CurrencyCode` | `DocCurrency` |
| `InvoiceDetails.CreditorNumber` | `CrdNo`, `CrdNO`, `CRD_NR` |
| `InvoiceDetails.CreditorName` | `CrdName`, `CRDNAME1`, `CRD_NAME_1` |
| `InvoiceDetails.BankKey` | `BankPK` |
| `InvoiceDetails.Iban` / `QrIban` | `IBAN`, `DocIBAN`, `BankIban`, `BankIBAN`, `SPC_IBAN` / `QR_IBAN` |
| `InvoiceDetails.PaymentReference` | `ESR`, `QR_Reference`, `SPC_Reference` |
| `InvoiceDetails.HasOrder` | `IsWithOrder`, `IswithOrder`, `IstwitOrder` |
| `InvoiceDetails.OrderNumber` | `Bestellnummer`, `BestellNummer` |
| `InvoiceDetails.OrderItemCount` | `OrdItmPosCount` |
| `DocumentValues` (rows) | everything client-specific: `Liegenschaftsnummer/LiegenschaftsNr` (`PropertyNumber`), `Eigentuemernummer/EigentuemerNr` (`OwnerNumber`), `ID_Miet/MietverhaeltnisNr` (`TenancyNumber`), `Niederlassung` (`Branch`), `Abteilung` (`Department`), `Empfaenger` (`Recipient`), `Mandant/Mandat` (`Tenant`), `Buchungskreis` (`CompanyCode`), `Branch`, `ISTEC`, `V_Bon`, `Opa`, `Vertraulichkeit`, `Einschreiben`, `Nachsendung`, `NS_*`, `WorkflowStamp`, `Zuordnung`, `CommentId`, `TopId`, `CrdTopDefault`, `RoundTolerance`, `ROOTING(_CA)`, `MehrfachRechnung`, `PDF_searchable`, `EndDocDate`, `Abklaerung`, `SelfLern`, `Doc_UID`, `ReferenznummerArchiv`, `Contract_Number`, `Agency_Name`, `Einlageblatt`, `Trennblatt`, `Deckblatt`, `ArchivBoxNummer`, `Langzeitlage`, `obligatorische_physische_archivierung`, `VersendetAnNL`, `OrigPhysischAnNL`, `isExpress`, `Val_State`, `BackManagement`, `LiegenschaftVerwaltungsartCD` |

## Migration notes

- **Type coercion is the real work.** Dates/amounts live in `nvarchar(50)` (`BFH_Statistic.ExportDate`, all amounts), booleans in `nvarchar(5)`/`nchar(10)`/`int`. Migrate with `TRY_CONVERT` + a rejects table; do not assume clean values.
- Some columns changed meaning mid-life (`EM_Invoice.ExportEM` nvarchar vs. `ExportEM_dt` datetime; `PriveraPosteingang.*Datetime` nvarchar vs. `*_dt`). Always take the `_dt` twin when present.
- German enum values (`Art LIKE '%Document%'`, `Ja/Nein`, `true/false` strings) need a value map per column.
- Backup/snapshot tables (`*_old`, `*_2018_2021`, `EM_Invoice_20240924`, ...) are dropped, not migrated — they are dead copies.

## What this buys nexora

- `Statconfig` (`TableName`/`ExportColumn`/`ImportColumn`/`additionalCondition`) collapses into `Processes` rows: every dashboard query becomes one parameterized query over `Documents` (`ImportedAt`/`ExportedAt`/`DeletedAt IS NULL`) — the whole per-process `UNION ALL` string-building in `nx_lib/views/dashboard.py` goes away.
- `SearchConfig` doc-field search reads `DocumentValues`/`FieldValidationEvents` instead of per-client wide tables; MS02's PG mirror uses the same names, so the per-dialect SQL in `workitem_sources.py` shrinks to quoting style.
- The reporting source registry gets one stable schema to describe; semantic metrics (throughput, validation time, first-pass yield) become plain views instead of per-client expressions.
- New client onboarding = 1 `Clients` row + n `Processes` rows. No new tables, no new Statconfig plumbing, no nexora deploy.
