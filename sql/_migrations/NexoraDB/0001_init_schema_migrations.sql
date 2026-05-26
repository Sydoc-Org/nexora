-- Bootstrap: create dbo.SchemaMigrations.
-- The migration runner (scripts/db-migrate.py) records every applied migration
-- here, including this one. IF NOT EXISTS makes it safe to re-run.

IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE name = 'SchemaMigrations' AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TABLE dbo.SchemaMigrations (
        FileName  NVARCHAR(255) NOT NULL
            CONSTRAINT PK_SchemaMigrations PRIMARY KEY,
        AppliedAt DATETIME2     NOT NULL
            CONSTRAINT DF_SchemaMigrations_AppliedAt DEFAULT SYSUTCDATETIME(),
        AppliedBy NVARCHAR(128) NOT NULL
            CONSTRAINT DF_SchemaMigrations_AppliedBy DEFAULT SUSER_SNAME(),
        Checksum  BINARY(32)    NOT NULL
    );
END
GO
