/*
  Standardised Statistics DB schema ("sydoc_stat vNext")
  ======================================================
  One schema for all clients and processes. Replaces the per-client hand-grown
  tables (BFH_Statistic, EM_Invoice, PriveraPosteingang, ...) with a fixed core
  plus typed satellites. Naming rules and the full old->new mapping live in
  README.md next to this file.

  Conventions (apply to every future object):
    - Tables:   dbo.<PascalCase, plural>            e.g. dbo.Documents
    - Columns:  PascalCase, English, no type suffixes (_dt, _bi), no Anz/NS_ prefixes
    - PK:       <TableSingular>Id                    e.g. DocumentId
    - FK:       same name as the referenced PK
    - Times:    <Verb>edAt   datetime2(0)            ScannedAt, ImportedAt, ExportedAt
    - Users:    <Verb>edBy   nvarchar(50)            ScannedBy, DeletedBy
    - Dates:    <Noun>Date   date                    DocumentDate, VolumeDate
    - Flags:    Is<X> / Has<X>  bit
    - Money:    decimal(18,2); CurrencyCode char(3) ISO-4217
    - Text:     bounded nvarchar; nvarchar(max) only for truly unbounded values
  The MS02 Postgres mirror uses the exact same names, double-quoted PascalCase.
*/

------------------------------------------------------------------------------
-- Reference: who and what
------------------------------------------------------------------------------

CREATE TABLE dbo.Clients (
    ClientId        int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Clients PRIMARY KEY,
    ClientCode      nvarchar(50)  NOT NULL CONSTRAINT UQ_Clients_ClientCode UNIQUE,  -- 'bucherer', 'compass', 'privera', 'ms02', ...
    ClientName      nvarchar(100) NOT NULL
);

CREATE TABLE dbo.Processes (
    ProcessId        int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Processes PRIMARY KEY,
    ClientId         int           NOT NULL CONSTRAINT FK_Processes_Clients REFERENCES dbo.Clients (ClientId),
    ProcessCode      nvarchar(100) NOT NULL CONSTRAINT UQ_Processes_ProcessCode UNIQUE,  -- full Octo name, e.g. 'privera.03_Invoice_New'
    ProcessName      nvarchar(100) NOT NULL,
    ProcessType      nvarchar(25)  NOT NULL,   -- 'invoice' | 'mailroom' | 'scan' | 'archive' | 'other'
    OrganizationCode nvarchar(100) NULL,       -- Octo ORGANIZATION
    UnitCode         nvarchar(100) NULL,       -- Octo UNIT
    IsActive         bit           NOT NULL CONSTRAINT DF_Processes_IsActive DEFAULT (1)
);

------------------------------------------------------------------------------
-- Core fact: one row per processed document (workitem leaf)
------------------------------------------------------------------------------

CREATE TABLE dbo.Documents (
    DocumentId          bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Documents PRIMARY KEY,
    ProcessId           int           NOT NULL CONSTRAINT FK_Documents_Processes REFERENCES dbo.Processes (ProcessId),
    WorkitemId          nvarchar(50)  NULL,    -- source-system id (int in Octo, string elsewhere)
    ParentWorkitemId    nvarchar(50)  NULL,    -- batch / Sendung the document arrived in
    Barcode             nvarchar(100) NULL,
    ShipmentBarcode     nvarchar(100) NULL,
    DocumentType        nvarchar(50)  NULL,
    DocumentDate        date          NULL,    -- date printed on the document
    Channel             nvarchar(25)  NULL,    -- 'scan' | 'email' | 'sftp' | 'upload' | 'rest'
    FileName            nvarchar(400) NULL,
    PageCountScanned    int           NULL,
    PageCountProcessed  int           NULL,
    DocumentCount       int           NULL,    -- documents in the physical shipment
    AttachmentCount     int           NULL,

    -- lifecycle
    ScannedAt           datetime2(0)  NULL,
    ScannedBy           nvarchar(50)  NULL,
    ImportedAt          datetime2(0)  NULL,
    ExportedAt          datetime2(0)  NULL,
    DeletedAt           datetime2(0)  NULL,    -- replaces GeloeschtAm / additionalCondition filters
    DeletedBy           nvarchar(50)  NULL,
    NoExportReason      nvarchar(255) NULL,
    IsApproved          bit           NULL,
    IsDuplicate         bit           NULL,
    DuplicateCode       nvarchar(255) NULL,
    OriginalDestroyedOn date          NULL,    -- physical original shredded
    OriginalDestroyedBy nvarchar(50)  NULL,

    -- email channel metadata (NULL for non-email documents)
    EmailMessageId      nvarchar(255) NULL,
    EmailFrom           nvarchar(255) NULL,
    EmailTo             nvarchar(255) NULL,
    EmailSubject        nvarchar(255) NULL,

    Environment         nvarchar(10)  NULL     -- 'PROD' | 'INT'
);

CREATE INDEX IX_Documents_Process_ImportedAt ON dbo.Documents (ProcessId, ImportedAt) INCLUDE (ExportedAt, DeletedAt);
CREATE INDEX IX_Documents_Process_ExportedAt ON dbo.Documents (ProcessId, ExportedAt);
CREATE INDEX IX_Documents_WorkitemId         ON dbo.Documents (WorkitemId);

------------------------------------------------------------------------------
-- Multi-step validation (ValUserA/B/C, ValUserAdmin, ValUserApproved, ...)
------------------------------------------------------------------------------

CREATE TABLE dbo.ValidationSteps (
    ValidationStepId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ValidationSteps PRIMARY KEY,
    DocumentId       bigint        NOT NULL CONSTRAINT FK_ValidationSteps_Documents REFERENCES dbo.Documents (DocumentId),
    StepNumber       tinyint       NOT NULL,  -- 1, 2, 3 (was A, B, C)
    StepRole         nvarchar(25)  NOT NULL,  -- 'validation' | 'admin' | 'approval'
    ValidatedBy      nvarchar(50)  NULL,
    ValidatedAt      datetime2(0)  NULL,
    DurationSeconds  decimal(9,2)  NULL,
    Outcome          nvarchar(25)  NULL       -- 'completed' | 'deleted' | 'rejected' | 'deferred'
);

CREATE INDEX IX_ValidationSteps_DocumentId ON dbo.ValidationSteps (DocumentId);

------------------------------------------------------------------------------
-- Invoice satellite (1:1 with Documents, invoice-type processes only)
------------------------------------------------------------------------------

CREATE TABLE dbo.InvoiceDetails (
    DocumentId       bigint        NOT NULL CONSTRAINT PK_InvoiceDetails PRIMARY KEY
                                            CONSTRAINT FK_InvoiceDetails_Documents REFERENCES dbo.Documents (DocumentId),
    InvoiceNumber    nvarchar(50)  NULL,
    GrossAmount      decimal(18,2) NULL,
    NetAmount        decimal(18,2) NULL,
    VatAmount        decimal(18,2) NULL,
    AmountDifference decimal(18,2) NULL,
    CurrencyCode     char(3)       NULL,
    VatCode          nvarchar(50)  NULL,
    CreditorNumber   nvarchar(50)  NULL,
    CreditorName     nvarchar(255) NULL,
    BankKey          nvarchar(50)  NULL,      -- was BankPK
    Iban             nvarchar(34)  NULL,
    QrIban           nvarchar(34)  NULL,
    PaymentReference nvarchar(50)  NULL,      -- ESR / QR / SPC reference
    HasOrder         bit           NULL,      -- was IsWithOrder
    OrderNumber      nvarchar(50)  NULL,      -- was Bestellnummer
    OrderItemCount   int           NULL       -- was OrdItmPosCount
);

------------------------------------------------------------------------------
-- Client/process-specific values: extracted vs. final, one row per field
-- (absorbs the extractedX/X column pairs and every one-client oddball column)
------------------------------------------------------------------------------

CREATE TABLE dbo.DocumentValues (
    DocumentValueId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentValues PRIMARY KEY,
    DocumentId      bigint        NOT NULL CONSTRAINT FK_DocumentValues_Documents REFERENCES dbo.Documents (DocumentId),
    FieldCode       nvarchar(100) NOT NULL,  -- 'PropertyNumber', 'OwnerNumber', 'CompanyCode', ...
    ExtractedValue  nvarchar(max) NULL,      -- machine value before validation
    FinalValue      nvarchar(max) NULL,      -- value after validation
    CONSTRAINT UQ_DocumentValues UNIQUE (DocumentId, FieldCode)
);

------------------------------------------------------------------------------
-- Field-level validation telemetry
-- (union of all *_Collect_Field_Attributes tables, typed)
------------------------------------------------------------------------------

CREATE TABLE dbo.FieldValidationEvents (
    FieldValidationEventId  bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_FieldValidationEvents PRIMARY KEY,
    ProcessId               int           NOT NULL CONSTRAINT FK_FieldValidationEvents_Processes REFERENCES dbo.Processes (ProcessId),
    WorkitemId              nvarchar(50)  NULL,
    DocumentRef             nvarchar(255) NULL,   -- was DOCUMENT_ID
    DocumentName            nvarchar(255) NULL,
    DocumentType            nvarchar(50)  NULL,
    FieldName               nvarchar(100) NOT NULL,
    FieldDefinition         nvarchar(100) NULL,   -- was DEFNAME
    FieldType               nvarchar(50)  NULL,   -- was TYPE
    OccurredAt              datetime2(0)  NULL,   -- was TIME
    ValueBeforeValidation   nvarchar(max) NULL,
    StatusBeforeValidation  nvarchar(25)  NULL,
    MessageBeforeValidation nvarchar(max) NULL,
    ValueAfterValidation    nvarchar(max) NULL,
    StatusAfterValidation   nvarchar(25)  NULL,
    Result                  nvarchar(25)  NULL,
    IsSetByMachine          bit           NULL,
    IsUserVerified          bit           NULL,
    IsUserEntered           bit           NULL,
    IsUserModified          bit           NULL,
    HistorySource           nvarchar(50)  NULL,
    ValueOrigin             nvarchar(50)  NULL,
    IsFromCandidateList     bit           NULL,   -- was VALUE_FROM_CANDIDATE_LIST
    ExtractedWithSelfLearning bit         NULL,   -- was EXTRACTED_WITH_SL
    ConfidenceBest          decimal(5,4)  NULL,   -- was CONF_BEST_CANDIDATE
    ConfidenceSecond        decimal(5,4)  NULL    -- was CONF_2ND_CANDIDATE
);

CREATE INDEX IX_FieldValidationEvents_Process_OccurredAt ON dbo.FieldValidationEvents (ProcessId, OccurredAt);
CREATE INDEX IX_FieldValidationEvents_WorkitemId         ON dbo.FieldValidationEvents (WorkitemId);

------------------------------------------------------------------------------
-- Multi-target exports (ELSY: AWS + REST legs; others have one row or none)
------------------------------------------------------------------------------

CREATE TABLE dbo.DocumentExports (
    DocumentExportId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DocumentExports PRIMARY KEY,
    DocumentId       bigint        NOT NULL CONSTRAINT FK_DocumentExports_Documents REFERENCES dbo.Documents (DocumentId),
    Target           nvarchar(50)  NOT NULL,  -- 'aws' | 'rest' | 'sap' | 'sftp' | ...
    ExportedAt       datetime2(0)  NOT NULL,
    FileName         nvarchar(400) NULL
);

CREATE INDEX IX_DocumentExports_DocumentId ON dbo.DocumentExports (DocumentId);

------------------------------------------------------------------------------
-- File transfer / file state log (SFTP actions, StadtBiel file requests)
------------------------------------------------------------------------------

CREATE TABLE dbo.TransferEvents (
    TransferEventId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_TransferEvents PRIMARY KEY,
    ProcessId       int           NOT NULL CONSTRAINT FK_TransferEvents_Processes REFERENCES dbo.Processes (ProcessId),
    ExternalRef     nvarchar(100) NULL,   -- was FileID
    FileName        nvarchar(400) NULL,
    FilePath        nvarchar(400) NULL,
    Action          nvarchar(100) NOT NULL,  -- was Action / State
    RequestedBy     nvarchar(100) NULL,      -- was DemandedBy
    OccurredAt      datetime2(0)  NOT NULL
);

CREATE INDEX IX_TransferEvents_Process_OccurredAt ON dbo.TransferEvents (ProcessId, OccurredAt);

------------------------------------------------------------------------------
-- Pre-aggregated daily counters (Scan2Mail feeds deliver totals, not documents)
------------------------------------------------------------------------------

CREATE TABLE dbo.DailyVolumes (
    DailyVolumeId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DailyVolumes PRIMARY KEY,
    ProcessId     int  NOT NULL CONSTRAINT FK_DailyVolumes_Processes REFERENCES dbo.Processes (ProcessId),
    VolumeDate    date NOT NULL,
    DocumentCount int  NOT NULL,
    PageCount     int  NOT NULL,
    CONSTRAINT UQ_DailyVolumes UNIQUE (ProcessId, VolumeDate)
);

------------------------------------------------------------------------------
-- License metering (was DPSLicenseCounter)
------------------------------------------------------------------------------

CREATE TABLE dbo.LicenseUsage (
    LicenseUsageId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_LicenseUsage PRIMARY KEY,
    ProcessId      int           NOT NULL CONSTRAINT FK_LicenseUsage_Processes REFERENCES dbo.Processes (ProcessId),
    WorkitemId     nvarchar(50)  NULL,
    ProcessState   nvarchar(100) NULL,
    DocumentCount  int           NULL,
    PageCount      int           NULL,
    CountedAt      datetime2(0)  NOT NULL
);

CREATE INDEX IX_LicenseUsage_Process_CountedAt ON dbo.LicenseUsage (ProcessId, CountedAt);

------------------------------------------------------------------------------
-- Time tracking (was TimeTool — separate domain, standardised but kept apart)
------------------------------------------------------------------------------

CREATE TABLE dbo.TimeEntries (
    TimeEntryId    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_TimeEntries PRIMARY KEY,
    ClientId       int           NOT NULL CONSTRAINT FK_TimeEntries_Clients REFERENCES dbo.Clients (ClientId),
    ProjectPackage nvarchar(100) NULL,   -- was Projektpaket
    Task           nvarchar(100) NULL,   -- was Aufgabe
    EntryDate      date          NOT NULL,
    Description    nvarchar(500) NULL,
    Hours          decimal(6,2)  NOT NULL,
    EnteredBy      nvarchar(100) NOT NULL  -- was Benutzer
);

CREATE INDEX IX_TimeEntries_Client_EntryDate ON dbo.TimeEntries (ClientId, EntryDate);
