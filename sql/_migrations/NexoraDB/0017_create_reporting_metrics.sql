-- 0017_create_reporting_metrics.sql
-- Reporting semantic layer (Slice 1): canonical metrics. A metric is a named
-- server-side aggregation (Aggregation over BaseField) bound to a registered
-- source (ReportingSources.Code or a code-default source id). Used in a report
-- definition's `metrics` list; the existing `columns` become the GROUP BY.
-- Curated via the /reporting/metrics admin page, gated reporting.semantic.admin.
-- FilterJson is reserved for a later slice (stored, not yet applied).

IF OBJECT_ID(N'dbo.ReportingMetrics', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingMetrics (
        MetricID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingMetrics PRIMARY KEY,
        Code         NVARCHAR(64) NOT NULL CONSTRAINT UQ_ReportingMetrics_Code UNIQUE,
        SourceId     NVARCHAR(64) NOT NULL,
        Label        NVARCHAR(120) NOT NULL,
        Aggregation  NVARCHAR(16) NOT NULL,
        BaseField    NVARCHAR(128) NULL,
        FilterJson   NVARCHAR(MAX) NULL,
        Description  NVARCHAR(512) NULL,
        Format       NVARCHAR(16) NULL,
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportingMetrics_Enabled DEFAULT 1,
        SortOrder    INT NOT NULL CONSTRAINT DF_ReportingMetrics_SortOrder DEFAULT 100,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingMetrics_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_ReportingMetrics_Aggregation
            CHECK (Aggregation IN ('count','count_distinct','sum','avg','min','max'))
    );
END;
GO

-- Admin permission for the metrics-registry UI/endpoints, granted to every
-- profile that already grants admin.view ('A'). Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.semantic.admin', 'Reporting: manage the canonical metrics registry'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.semantic.admin');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.semantic.admin'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO

-- Worked example over the docprocessing source (always present). Idempotent.
INSERT INTO dbo.ReportingMetrics (Code, SourceId, Label, Aggregation, BaseField, Description, Format, SortOrder)
SELECT 'doc_count', 'docprocessing', 'Document count', 'count', NULL,
       'Number of documents (rows) in scope', 'int', 10
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'doc_count');
GO
