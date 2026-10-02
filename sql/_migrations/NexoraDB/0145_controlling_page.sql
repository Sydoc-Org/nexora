-- 0145_controlling_page.sql  (#433)
-- The Sydoc Controlling page (/controlling): per client stream, the hours
-- booked in BPS x an hourly rate = cost, against what was invoiced in Bexio
-- (excl. VAT) = margin. It replaces the hand-filled
-- Projektcontrolling_Betriebskosten.xlsx workbook.
--
-- 1. controlling.view -- its own area, Global Admin only like finance.view and
--    bps.view: the page names every client's margin and reads BPS unscoped.
--    Enterprise Admin picks it up through the 0106 trigger. Rates are edited
--    by finance.month.edit holders (no new code).
-- 2. dbo.FinanceRates -- the rates the cost is computed with, by validity:
--    Kind 'hourly' (CHF per hour) and 'fte_day_hours' (hours of one FTE per
--    working day, for the FTE line). StreamKey NULL is the default; a row
--    with a StreamKey overrides it for that stream. ValidFrom / ValidTo are
--    first days of months (ValidTo NULL = open-ended, inclusive).
-- 3. dbo.ControllingStreamProjects -- which Bexio project an invoice must
--    carry to count for a stream. Invoice titles do not tell the streams
--    apart ("August 2026", "Support August 2026"); the Bexio project does,
--    support invoices included. Project ids are Bexio's own, read on
--    2026-10-01 from the invoices of 2025-2026 (#433 comment).
--
-- Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'controlling.view', N'View the Sydoc Controlling page (margin per client: BPS hours x rate against Bexio invoices)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'controlling.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'controlling.view'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO

IF OBJECT_ID(N'dbo.FinanceRates', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FinanceRates (
        RateId    INT IDENTITY(1,1) NOT NULL,
        Kind      NVARCHAR(20)  NOT NULL,
        StreamKey NVARCHAR(50)  NULL,
        Value     DECIMAL(10,2) NOT NULL,
        ValidFrom DATE          NOT NULL,
        ValidTo   DATE          NULL,
        ChangedAt DATETIME2(0)  NOT NULL CONSTRAINT DF_FinanceRates_ChangedAt DEFAULT SYSUTCDATETIME(),
        ChangedBy NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_FinanceRates PRIMARY KEY (RateId),
        CONSTRAINT CK_FinanceRates_Kind CHECK (Kind IN (N'hourly', N'fte_day_hours')),
        CONSTRAINT CK_FinanceRates_Value CHECK (Value > 0),
        CONSTRAINT CK_FinanceRates_Range CHECK (ValidTo IS NULL OR ValidTo >= ValidFrom)
    );
END;
GO

-- The workbook's rate since Jul 2021: 85 CHF/h. 8.4 h is a BPS working day
-- (an absence day is booked as 8.4 h).
INSERT INTO dbo.FinanceRates (Kind, StreamKey, Value, ValidFrom, ChangedBy)
SELECT v.Kind, NULL, v.Value, '2025-01-01', N'migration 0145'
FROM (VALUES (N'hourly', 85.00), (N'fte_day_hours', 8.40)) AS v (Kind, Value)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.FinanceRates r WHERE r.Kind = v.Kind AND r.StreamKey IS NULL
);
GO

IF OBJECT_ID(N'dbo.ControllingStreamProjects', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ControllingStreamProjects (
        ProjectId INT           NOT NULL,
        StreamKey NVARCHAR(50)  NOT NULL,
        Note      NVARCHAR(200) NULL,
        LinkedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_ControllingStreamProjects_LinkedAt DEFAULT SYSUTCDATETIME(),
        LinkedBy  NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_ControllingStreamProjects PRIMARY KEY (ProjectId)
    );
END;
GO

INSERT INTO dbo.ControllingStreamProjects (ProjectId, StreamKey, Note, LinkedBy)
SELECT v.ProjectId, v.StreamKey, v.Note, N'migration 0145'
FROM (VALUES
    (8,  N'elektro_material',    N'Posteingang - Aufbereitung & Scanning Vertrag 1.3'),
    (5,  N'compass',             N'5.08 Projekt KrediFlow'),
    (10, N'privera_posteingang', N'TP01 - Digitalisierung der täglichen Post'),
    (46, N'privera_posteingang', N'Rücksendung angeforderte Dokumente (Postpakete)'),
    (4,  N'privera_invoice',     N'TP03 - Digitalisierung der täglichen Kreditorenrechnungen'),
    (17, N'privera_neuzugaenge', N'Liegenschaften Neuzugänge gemäss Vertrag 5.12'),
    (58, N'frigemo',             N'Rechnungsverarbeitung'),
    (7,  N'zhaw',                N'ePosting ZHAW Verarbeitung (Aveniq AG)'),
    (74, N'zhaw',                N'ePosting ZHAW Verarbeitung (Xpert Consulting AG)'),
    (6,  N'bfh',                 N'ePosting Verrechnung DocProStar (Aveniq AG)'),
    (73, N'bfh',                 N'ePosting Verrechnung DocProStar (Xpert Consulting AG)'),
    (33, N'bfh',                 N'Validierungs-Service (BFH direct)'),
    (32, N'bucherer',            N'Easy Tax'),
    (43, N'bucherer',            N'Bucherer International'),
    (45, N'bucherer',            N'Matchingtabelle ProConcept Bestellnummer versus PO-Number'),
    (12, N'mediamarkt',          N'Belegdigitalisierung')
) AS v (ProjectId, StreamKey, Note)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.ControllingStreamProjects p WHERE p.ProjectId = v.ProjectId
);
GO
