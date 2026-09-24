-- 0011_document_sap_metadata.sql
-- Issue #220, phase 4b: move the populated SAP columns out of the hot table
-- into a 1:1 side table (D6). Copy only -- 0012 does the dropping, so this
-- migration destroys nothing and can be checked before anything is lost.
--
-- Measured on INT 2026-09-10 (2,682,707 rows). Eleven DOC_SAP* columns:
--   populated on 3,719 rows (0.14%): DOC_SAPComps, DOC_SAPCompSize,
--     DOC_SAPContType, DOC_SAPDocId, DOC_SAPDocProt, DOC_SAPType
--   never written at all (0 non-null): DOC_SAPCompCharset, DOC_SAPCompCreated,
--     DOC_SAPCompModified, DOC_SAPCompVersion, DOC_SAPDocDate
-- (The plan had this 5/6 the other way round; these are today's numbers.)
--
-- NAMING NOTE. The foreign key is DocumentRecordId -> Documents.Id, not
-- "DocumentId" as rule D2 would give. Two reasons: Documents already has a
-- column literally called DocumentId holding the external GUID, so a child
-- column of that name would invite a wrong join; and Documents.DocumentId is
-- covered by a *filtered* unique index, which SQL Server will not accept as a
-- foreign-key target anyway.
--
-- Widths are the measured maxima rounded up, not the varchar(100) the source
-- columns carry: SapComponents 4, SapComponentSize 6, SapContentType 15,
-- SapDocumentId 32, SapDocumentProtection 4, SapType 3.
--
-- Idempotent.

IF OBJECT_ID(N'dbo.DocumentSapMetadata', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.DocumentSapMetadata (
        DocumentRecordId      int          NOT NULL,
        SapComponents         varchar(20)  NULL,
        SapComponentSize      varchar(20)  NULL,
        SapContentType        varchar(50)  NULL,
        SapDocumentId         varchar(64)  NULL,
        SapDocumentProtection varchar(20)  NULL,
        SapType               varchar(20)  NULL,
        CONSTRAINT PK_DocumentSapMetadata PRIMARY KEY CLUSTERED (DocumentRecordId),
        CONSTRAINT FK_DocumentSapMetadata_Documents FOREIGN KEY (DocumentRecordId)
            REFERENCES dbo.Documents (Id)
    );
END
GO

-- Only the rows that actually carry SAP data. Re-runnable: rows already moved
-- are skipped, so a partial run can simply be repeated.
INSERT INTO dbo.DocumentSapMetadata
    (DocumentRecordId, SapComponents, SapComponentSize, SapContentType,
     SapDocumentId, SapDocumentProtection, SapType)
SELECT d.Id, d.DOC_SAPComps, d.DOC_SAPCompSize, d.DOC_SAPContType,
       d.DOC_SAPDocId, d.DOC_SAPDocProt, d.DOC_SAPType
FROM dbo.Documents d
WHERE (d.DOC_SAPComps    IS NOT NULL OR d.DOC_SAPCompSize IS NOT NULL
    OR d.DOC_SAPContType IS NOT NULL OR d.DOC_SAPDocId    IS NOT NULL
    OR d.DOC_SAPDocProt  IS NOT NULL OR d.DOC_SAPType     IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM dbo.DocumentSapMetadata m WHERE m.DocumentRecordId = d.Id);
GO

-- Fail loudly rather than let 0012 drop columns whose contents did not arrive.
DECLARE @src int = (
    SELECT COUNT(*) FROM dbo.Documents
    WHERE DOC_SAPComps IS NOT NULL OR DOC_SAPCompSize IS NOT NULL
       OR DOC_SAPContType IS NOT NULL OR DOC_SAPDocId IS NOT NULL
       OR DOC_SAPDocProt IS NOT NULL OR DOC_SAPType IS NOT NULL);
DECLARE @dst int = (SELECT COUNT(*) FROM dbo.DocumentSapMetadata);
IF @src <> @dst
    THROW 50221, 'Migration 0011: DocumentSapMetadata row count does not match the populated DOC_SAP* rows in dbo.Documents. Do not apply 0012 until this is resolved.', 1;
PRINT CONCAT('Migration 0011: ', @dst, ' SAP row(s) in DocumentSapMetadata.');
GO
