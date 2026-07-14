-- 0038_create_api_keys.sql
-- Per-client API keys for the external machine-to-machine JSON API v1
-- (GET /api/v1/stats/today). Only the SHA-256 hex digest of the random
-- 32-byte token is stored (high-entropy key -> bcrypt unnecessary);
-- issuance is manual in v1 via scripts/new-api-key.py (prints the raw
-- token once + the INSERT). ProcessList is a comma-separated list of
-- full dbo.Statconfig ProcessName values (e.g. 'sydoc.05_PDBS') defining
-- the key's stats scope -- the same strings the dashboard's
-- dashboard.filter.process.* permission codes resolve to. ClientCode is
-- an audit label (no FK, not validated against the CLIENTS registry).
-- Disabled keys (Enabled = 0) answer exactly like unknown keys (401) --
-- no existence oracle. No key-management UI, no OAuth, no usage
-- dashboard (YAGNI, v1).
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ApiKeys' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.ApiKeys (
        ID          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ApiKeys PRIMARY KEY,
        KeyHash     CHAR(64) NOT NULL CONSTRAINT UQ_ApiKeys_KeyHash UNIQUE,
        ClientCode  NVARCHAR(32) NOT NULL,
        Label       NVARCHAR(255) NULL,
        ProcessList NVARCHAR(MAX) NOT NULL,
        Enabled     BIT NOT NULL CONSTRAINT DF_ApiKeys_Enabled DEFAULT (1),
        CreatedAt   DATETIME2 NOT NULL CONSTRAINT DF_ApiKeys_CreatedAt DEFAULT (SYSUTCDATETIME()),
        LastUsedAt  DATETIME2 NULL
    );
END
GO
