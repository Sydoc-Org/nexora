-- 0139_finance_parity_and_close.sql  (#415)
-- The Sydoc Finance page (#408, 0138) must reproduce the monthly billing
-- workbooks exactly. A reconciliation against PROD (2026-05/07/08, #415) found
-- two definitions that differed from the workbooks and one thing no definition
-- can fix; this migration settles all three.
--
-- 1. PRIVERA MAIL FOLLOWS THE WORKBOOK'S FILE-NAME RULE
-- 0132 keyed the Mail measure on DocSource = 'MAIL' alone and noted a small
-- August gap (11,764 vs 11,759) as "not papered over", blaming rows without a
-- Mandant. The real rule is the workbook's Mail pivot filter: it ticks file
-- names ('M-%'), and a MAIL row with no FileName is never ticked. Adding
-- FileName IS NOT NULL reproduces the published figure in every month checked
-- (May 11,669, July 14,945, August 11,759). Invoicing bills the workbook, so the
-- measure now is the workbook. FileName joins the catalog so the filter resolves
-- (it is a scan file name, nothing sensitive -- amounts and bank columns stay
-- out, as 0132 decided).
--
-- 2. MEDIAMARKT BATCHES COUNT ONLY FILLED ROWS
-- The protocol pre-types the next batch numbers before they are scanned; a
-- placeholder row (no pieces yet) is not a batch. The count now skips rows
-- whose Pieces is NULL, the same thing the protocol's Monatstotal counts.
--
-- 3. MONTH CLOSE
-- Elektro-Material and Compass rows are re-exported / re-uploaded after a
-- month has been invoiced, and the source overwrites the date, so a closed
-- month read live later drifts from what was billed (EM: 2 / 30 / 2 / 103
-- documents in May-August 2026). No filter can undo that -- the history is not
-- kept anywhere. dbo.FinanceMonthClose stores the page payload of every section
-- at the moment accounting closes the month; a closed month is read from it,
-- and the live figures are only shown as a difference next to it.
-- finance.month.edit gates closing and reopening. Global Admin gets it here (same
-- reason as 0138); Enterprise Admin through the 0106 trigger. Never a customer.
--
-- Idempotent.

UPDATE dbo.ReportingSources
SET ColumnsJSON = JSON_MODIFY(
        ColumnsJSON, 'append $',
        JSON_QUERY(N'{"field":"FileName","label":"File name","type":"string","filterable":true,"sortable":true}'))
WHERE Code = 'privera_invoice'
  AND ColumnsJSON NOT LIKE N'%"field":"FileName"%';
GO

UPDATE dbo.ReportingMetrics
SET FilterJson = N'[{"field":"DocSource","op":"eq","value":"MAIL"},{"field":"FileName","op":"is_not_null"}]',
    Description = N'Documents that arrived by e-mail: DocSource MAIL with a file name -- the rule of the Rechnungseingang workbook''s Mail pivot, which drops MAIL rows without a file name (0139).'
WHERE Code = 'privera_mail_documents';
GO

UPDATE dbo.ReportingMetrics
SET FilterJson = N'[{"field":"Pieces","op":"is_not_null"}]',
    Description = N'Batches scanned: protocol rows with a piece count. Pre-typed batch numbers without pieces are placeholders, not batches (0139).'
WHERE Code = 'mediamarkt_batches';
GO

IF OBJECT_ID(N'dbo.FinanceMonthClose', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FinanceMonthClose (
        Month      CHAR(7)       NOT NULL,
        SectionKey VARCHAR(64)   NOT NULL,
        Payload    NVARCHAR(MAX) NOT NULL,
        ClosedAt   DATETIME2(0)  NOT NULL CONSTRAINT DF_FinanceMonthClose_ClosedAt DEFAULT SYSUTCDATETIME(),
        ClosedBy   NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_FinanceMonthClose PRIMARY KEY (Month, SectionKey)
    );
END;
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT N'finance.month.edit', N'Close and reopen a month on the Sydoc Finance page (freezes its figures)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'finance.month.edit');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'finance.month.edit'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO
