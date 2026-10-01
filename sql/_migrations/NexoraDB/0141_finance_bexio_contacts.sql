-- 0141_finance_bexio_contacts.sql  (#423)
-- The Sydoc Finance page shows, next to each month's figures, what was
-- invoiced in Bexio (read-only: nexora never writes to Bexio). Bexio knows
-- its customers as contacts; the page knows them as the Finance client names
-- of nx_lib/finance.py (Section.client: 'Elektro-Material', 'Privera', ...).
-- This table links the two.
--
-- One row per Bexio contact: a contact belongs to at most one Finance client
-- (the primary key), a client may have several contacts (Privera's branches
-- could be billed to separate contacts). Rows are added and removed from the
-- page by holders of finance.month.edit; the contact id is Bexio's own.
--
-- Supersedes nothing: the retired invoices page's dbo.ClientInvoices mapping
-- (bexioClientId per ClientName, customer-facing) was dropped in #98.
--
-- Idempotent.

IF OBJECT_ID(N'dbo.FinanceBexioContacts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FinanceBexioContacts (
        ContactId INT           NOT NULL,
        Client    NVARCHAR(100) NOT NULL,
        LinkedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_FinanceBexioContacts_LinkedAt DEFAULT SYSUTCDATETIME(),
        LinkedBy  NVARCHAR(100) NOT NULL,
        CONSTRAINT PK_FinanceBexioContacts PRIMARY KEY (ContactId)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_FinanceBexioContacts_Client'
      AND object_id = OBJECT_ID(N'dbo.FinanceBexioContacts')
)
    CREATE INDEX IX_FinanceBexioContacts_Client ON dbo.FinanceBexioContacts (Client);
GO
