-- 0079: dbo.Clients runtime-source registry (#98 phase 4).
-- Replaces the hardcoded CLIENTS dict in nx_lib/clients.py::_build_clients() so a
-- customer riding the existing 'default' or 'ms02' runtime can be onboarded without
-- a deploy. Non-secret facts only -- Octo secrets and DB passwords stay in
-- env/{ENV}.env, referenced by the SecretRef key prefix (see spec D3). Nothing reads
-- this table yet; that lands in the next task.
--
-- Seed mirrors _build_clients() exactly as of 2026-08-27:
--   default -> engine_octo_db (tsql), stats/docfields -> engine_statistics_db (tsql)
--   ms02    -> engine_ms02_pg (postgres), stats -> engine_ms02_stats_pg,
--              docfields -> engine_ms02_docfields_pg, SecretRef 'MS02'
-- OctoDomain stays NULL for both seeded rows -- the domain is still read from
-- cfg.OCTO_DOMAIN / cfg.MS02_OCTO_DOMAIN in phase A; the column exists for
-- clients added later through the admin UI.

IF OBJECT_ID('dbo.Clients', 'U') IS NULL
CREATE TABLE dbo.Clients (
    ClientCode          NVARCHAR(50)  NOT NULL,
    DisplayName         NVARCHAR(100) NOT NULL,
    Dialect             NVARCHAR(20)  NOT NULL,   -- 'tsql' | 'postgres'
    RuntimeEngineKey    NVARCHAR(50)  NOT NULL,   -- name of an engine in nx_lib/db.py
    StatsEngineKey      NVARCHAR(50)  NULL,
    StatsDialect        NVARCHAR(20)  NULL,
    DocfieldsEngineKey  NVARCHAR(50)  NULL,
    DocfieldsDialect    NVARCHAR(20)  NULL,
    OctoDomain          NVARCHAR(255) NULL,
    SecretRef           NVARCHAR(50)  NULL,       -- env-key prefix; NULL = unprefixed OCTO_*
    IsActive            BIT NOT NULL CONSTRAINT DF_Clients_IsActive DEFAULT (1),
    CONSTRAINT PK_Clients PRIMARY KEY CLUSTERED (ClientCode)
);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Clients)
INSERT INTO dbo.Clients (ClientCode, DisplayName, Dialect, RuntimeEngineKey,
    StatsEngineKey, StatsDialect, DocfieldsEngineKey, DocfieldsDialect,
    OctoDomain, SecretRef)
VALUES
    ('default', 'Default', 'tsql', 'engine_octo_db',
        'engine_statistics_db', 'tsql', 'engine_statistics_db', 'tsql',
        NULL, NULL),
    ('ms02', 'MS02', 'postgres', 'engine_ms02_pg',
        'engine_ms02_stats_pg', 'postgres', 'engine_ms02_docfields_pg', 'postgres',
        NULL, 'MS02');
GO
