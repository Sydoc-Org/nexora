-- 0010_reporting_sources_registry.sql
-- DB-backed reporting source registry. Rows in dbo.ReportingSources augment or
-- override the code-defined source defaults (nx_lib/reporting/sources.py): an
-- admin can relabel, enable/disable, reorder or re-permission an existing source
-- and register new ones without a code change. Curated execution binds to a code
-- "Provider": 'docprocessing' (the bespoke Statconfig source) or 'table' (the
-- generic single-object provider, whose column catalog is ColumnsJSON and whose
-- read target is BaseObject). Gated by a new reporting.admin.sources permission.

IF OBJECT_ID(N'dbo.ReportingSources', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingSources (
        SourceID     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ReportingSources PRIMARY KEY,
        Code         NVARCHAR(64) NOT NULL CONSTRAINT UQ_ReportingSources_Code UNIQUE,
        Kind         NVARCHAR(16) NOT NULL,             -- 'curated' | 'sql'
        Label        NVARCHAR(120) NOT NULL,
        Permission   NVARCHAR(128) NOT NULL,
        Engine       NVARCHAR(32) NULL,                 -- nexora|statistics|generali|octopus
        Target       NVARCHAR(32) NULL,                 -- SQL sandbox target key
        Provider     NVARCHAR(32) NULL,                 -- curated provider: docprocessing|table
        BaseObject   NVARCHAR(256) NULL,                -- 'Db.schema.object' for the table provider
        ColumnsJSON  NVARCHAR(MAX) NULL,                -- [{field,label,type,filterable,sortable}]
        Enabled      BIT NOT NULL CONSTRAINT DF_ReportingSources_Enabled DEFAULT 1,
        SortOrder    INT NOT NULL CONSTRAINT DF_ReportingSources_SortOrder DEFAULT 100,
        CreatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingSources_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2 NOT NULL CONSTRAINT DF_ReportingSources_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT CK_ReportingSources_Kind CHECK (Kind IN ('curated', 'sql'))
    );
END;
GO

-- Admin permission for the source-registry UI/endpoints, granted to every profile
-- that already grants admin.view ('A'). Idempotent.
INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.admin.sources', 'Reporting: manage the data-source registry'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'reporting.admin.sources');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.admin.sources'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
