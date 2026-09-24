-- 0010_documents_typed_columns.sql
-- Issue #220, phase 4a: give dbo.Documents real typed columns for the four
-- values that have always been strings. Purely additive -- every original
-- string column stays exactly as it is (D7).
--
-- THESE ARE COMPUTED COLUMNS, not backfilled ones. The plan called for a new
-- column backfilled by this migration; a computed column is the same thing
-- without the failure mode. A backfilled column is correct on the day it ships
-- and wrong from the next import onwards unless csvToSql.ps1 is taught to
-- write it too. One expression, defined once, can never drift.
-- ponytail: not PERSISTED. Non-persisted costs nothing to add (no size-of-data
-- ALTER, no lock, no storage) and these columns are read over at most 13k
-- non-null rows. If a report over Amount or VoucherDate ever needs an index or
-- shows up in a scan profile, add PERSISTED -- the expressions are
-- deterministic and precise, so that is a one-line change.
--
-- Measured on the live INT copy 2026-09-10, 2,682,707 rows. Every rule below
-- was checked against the real data first, and two of the plan's were wrong:
--
--   Quantity   the plan said `int`. The 302 values it called "unconvertible"
--              are 0.102, 0.469, 0.987 -- real fractional quantities, and
--              `int` would have thrown every one away. Worse, there are 2,297
--              EMPTY STRINGS in the column and TRY_CONVERT(int, '') returns
--              **0**, not NULL, so the plan's rule would have written 2,297
--              fabricated zeros into a quantity column. With NULLIF and
--              decimal(18,3): 304 real values, 304 converted, RESIDUAL 0.
--
--   Amount     the plan assumed mangled money needing a cleaning rule. It is
--              not money. Of 9,531 non-blank values, 9,183 are the literal
--              'CH04' and the rest are 'CH00', 'CH70', 'LI00', 'CH96' --
--              IBAN country-and-checksum prefixes. Only **207** are numbers
--              (60,0 / 41,95 / 160,7 / max 13224.00). RESIDUAL 9,324, and no
--              cleaning rule can fix it: the source system is writing the
--              wrong field. The owner asked for the column anyway, so here it
--              is -- 97.8% NULL, and honest about why. The raw strings are
--              untouched in AmountText. **This wants raising with Generali.**
--
--   VoucherDate  694 non-null, format 'dd.MM.yyyy HH:mm'. Style 104 parses
--                all 694. RESIDUAL 0. (The plan's worry about 401 failures
--                does not reproduce.) Style 104 is explicit, which is what
--                makes the expression deterministic.
--
--   IsPending    579,532 'True', 1,321,167 'False', 782,008 NULL, and ZERO
--                other values. The NULLs stay NULL: unknown is not false.
--
-- Idempotent.

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

-- 207 of 9,531 non-blank AmountText values parse. NULLIF keeps the 4,138
-- empty strings out; the apostrophe is the Swiss thousands separator.
IF COL_LENGTH(N'dbo.Documents', N'Amount') IS NULL
    ALTER TABLE dbo.Documents ADD Amount AS
        TRY_CONVERT(decimal(18,2),
            REPLACE(REPLACE(REPLACE(NULLIF(LTRIM(RTRIM(AmountText)), ''), '''', ''), ' ', ''), ',', '.'));
GO

-- 304 of 304 non-blank QuantityText values parse.
IF COL_LENGTH(N'dbo.Documents', N'Quantity') IS NULL
    ALTER TABLE dbo.Documents ADD Quantity AS
        TRY_CONVERT(decimal(18,3),
            REPLACE(NULLIF(LTRIM(RTRIM(QuantityText)), ''), ',', '.'));
GO

-- 694 of 694 non-blank VoucherDateText values parse with style 104 (dd.mm.yyyy).
IF COL_LENGTH(N'dbo.Documents', N'VoucherDate') IS NULL
    ALTER TABLE dbo.Documents ADD VoucherDate AS
        TRY_CONVERT(date, NULLIF(LTRIM(RTRIM(VoucherDateText)), ''), 104);
GO

-- 'True'/'False' only. NULL stays NULL -- unknown is not false.
IF COL_LENGTH(N'dbo.Documents', N'IsPending') IS NULL
    ALTER TABLE dbo.Documents ADD IsPending AS
        CASE PendingText WHEN 'True' THEN CONVERT(bit, 1) WHEN 'False' THEN CONVERT(bit, 0) END;
GO

-- Expose the four on the canonical read view. v_ReportJobJoinDefinitions is a
-- compat view and deliberately does NOT get them: it exists to look exactly
-- like the old world until phase 6 drops it.
CREATE OR ALTER VIEW dbo.v_Documents
AS
SELECT
    [ScanCaseId],
    [ScanCaseFolderName],
    [DocumentId],
    [EnvelopeId],
    [CaseId],
    [DOC_JOURNAL_ID],
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
    [DOC_DOKUMENT_URL],
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
