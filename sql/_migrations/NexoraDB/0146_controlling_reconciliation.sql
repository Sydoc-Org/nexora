-- 0146_controlling_reconciliation.sql  (#433)
-- Corrections to 0145 from reconciling the Controlling page against the
-- Projektcontrolling workbook, Jan 2025 - Aug 2026 (the workbook is the truth):
--
-- 1. Bexio projects that are on no stream, on purpose. StreamKey becomes
--    nullable; NULL = excluded (not reported as "unassigned" either):
--      46  Postpakete -- postage passed through at cost, never workbook revenue;
--      6/73 DocProStar -- Aveniq's/Xpert's other mandants (BAC, RAN, HAP, ISB,
--           HSLU, AGV), not BFH. BFH is its direct invoice (project 33) only.
-- 2. dbo.ControllingInvoiceStreams -- a per-invoice override that beats the
--    project (NULL StreamKey = exclude the invoice). Seeded with RE-26780: a
--    Privera "Support September 2025" invoice tagged with the Posteingang
--    project that bills the Rechnungseingang support (Support Operator).
-- 3. dbo.ControllingCosts -- external costs of a stream month on top of the
--    hours (the workbook's "Digi-Texx Rechnungen" on Privera Invoice), entered
--    on the page by finance.month.edit holders. Seeded with the workbook's
--    Digi-Texx amounts Jul 2025 - May 2026, before Bexio held purchase bills.
-- 4. dbo.ControllingVendorStreams -- Bexio purchase bills whose vendor
--    contains Match (case-insensitive) are external costs of StreamKey in the
--    month of their bill date. Seeded: Digi-Texx -> Privera Rechnungseingang.
--
-- Idempotent.

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ControllingStreamProjects')
      AND name = N'StreamKey' AND is_nullable = 0
)
    ALTER TABLE dbo.ControllingStreamProjects ALTER COLUMN StreamKey NVARCHAR(50) NULL;
GO

UPDATE dbo.ControllingStreamProjects
SET StreamKey = NULL,
    Note = v.Note
FROM dbo.ControllingStreamProjects p
JOIN (VALUES
    (46, N'Rücksendung angeforderte Dokumente (Postpakete): postage at cost, not revenue'),
    (6,  N'ePosting Verrechnung DocProStar (Aveniq AG): other mandants, not BFH'),
    (73, N'ePosting Verrechnung DocProStar (Xpert Consulting AG): other mandants, not BFH')
) AS v (ProjectId, Note) ON v.ProjectId = p.ProjectId
WHERE p.StreamKey IS NOT NULL;
GO

IF OBJECT_ID(N'dbo.ControllingInvoiceStreams', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ControllingInvoiceStreams (
        InvoiceId INT           NOT NULL,
        InvoiceNr NVARCHAR(50)  NOT NULL,
        StreamKey NVARCHAR(50)  NULL,
        Note      NVARCHAR(200) NULL,
        LinkedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_ControllingInvoiceStreams_LinkedAt DEFAULT SYSUTCDATETIME(),
        LinkedBy  NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_ControllingInvoiceStreams PRIMARY KEY (InvoiceId)
    );
END;
GO

INSERT INTO dbo.ControllingInvoiceStreams (InvoiceId, InvoiceNr, StreamKey, Note, LinkedBy)
SELECT 707, N'RE-26780', N'privera_invoice',
       N'Support September 2025 (Support Operator) for Rechnungseingang, tagged with the Posteingang project',
       N'migration 0146'
WHERE NOT EXISTS (SELECT 1 FROM dbo.ControllingInvoiceStreams WHERE InvoiceId = 707);
GO

IF OBJECT_ID(N'dbo.ControllingCosts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ControllingCosts (
        CostId    INT IDENTITY(1,1) NOT NULL,
        Month     DATE          NOT NULL,
        StreamKey NVARCHAR(50)  NOT NULL,
        Label     NVARCHAR(200) NOT NULL,
        Amount    DECIMAL(12,2) NOT NULL,
        ChangedAt DATETIME2(0)  NOT NULL CONSTRAINT DF_ControllingCosts_ChangedAt DEFAULT SYSUTCDATETIME(),
        ChangedBy NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_ControllingCosts PRIMARY KEY (CostId),
        CONSTRAINT CK_ControllingCosts_Month CHECK (DAY(Month) = 1)
    );
    CREATE INDEX IX_ControllingCosts_Month ON dbo.ControllingCosts (Month);
END;
GO

INSERT INTO dbo.ControllingCosts (Month, StreamKey, Label, Amount, ChangedBy)
SELECT v.Month, N'privera_invoice', N'Digi-Texx', v.Amount, N'migration 0146 (workbook)'
FROM (VALUES
    ('2025-07-01', 4673.83),
    ('2025-08-01', 4601.42),
    ('2025-09-01', 4609.76),
    ('2025-10-01', 5713.26),
    ('2025-11-01', 5054.38),
    ('2025-12-01', 6913.90),
    ('2026-01-01', 4931.30),
    ('2026-02-01', 4869.62),
    ('2026-03-01', 5559.49),
    ('2026-04-01', 5573.79),
    ('2026-05-01', 4509.93)
) AS v (Month, Amount)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.ControllingCosts c
    WHERE c.Month = v.Month AND c.StreamKey = N'privera_invoice' AND c.Label = N'Digi-Texx'
);
GO

IF OBJECT_ID(N'dbo.ControllingVendorStreams', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ControllingVendorStreams (
        Match     NVARCHAR(100) NOT NULL,
        StreamKey NVARCHAR(50)  NOT NULL,
        Label     NVARCHAR(200) NOT NULL,
        LinkedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_ControllingVendorStreams_LinkedAt DEFAULT SYSUTCDATETIME(),
        LinkedBy  NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_ControllingVendorStreams PRIMARY KEY (Match)
    );
END;
GO

INSERT INTO dbo.ControllingVendorStreams (Match, StreamKey, Label, LinkedBy)
SELECT N'digi-texx', N'privera_invoice', N'Digi-Texx', N'migration 0146'
WHERE NOT EXISTS (SELECT 1 FROM dbo.ControllingVendorStreams WHERE Match = N'digi-texx');
GO
