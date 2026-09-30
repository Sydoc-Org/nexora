-- 0141_admin_seed_int.sql
-- INT-only dev tooling: the admin overview's *Seed INT data* / *Clear seed*
-- buttons (nx_lib/seed.py, nx_lib/views/admin/seed.py) fill collector-owned
-- tables nexora only reads (dbo.BacklogHistory on the Statistics DB) with
-- synthetic history, and delete exactly those rows again.
--
-- dbo.SeedRuns is the ledger that makes "delete only what was seeded" exact:
-- every run stores the keys of the rows it wrote (RowKeys, JSON), and clearing
-- deletes rows matching those keys and nothing else. The table exists on every
-- environment because NexoraDB is migrated everywhere, but it is only ever
-- written on INT: the routes 404 outside ENVIRONMENT=INT and the seed module
-- refuses any server whose name looks like production.
--
-- admin.seed.manage gates the buttons and routes. Global Admin gets it here;
-- Enterprise Admin picks it up through the 0106 trigger. Never a customer
-- profile. Idempotent.

IF OBJECT_ID(N'dbo.SeedRuns', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.SeedRuns (
        RunID       INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_SeedRuns PRIMARY KEY,
        Seeder      NVARCHAR(50)   NOT NULL,
        TargetTable NVARCHAR(128)  NOT NULL,
        Days        INT            NOT NULL,
        RowsWritten INT            NOT NULL,
        RowKeys     NVARCHAR(MAX)  NOT NULL,
        SeededAt    DATETIME2(0)   NOT NULL CONSTRAINT DF_SeedRuns_SeededAt DEFAULT SYSDATETIME(),
        SeededBy    NVARCHAR(100)  NULL
    );
END;
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT N'admin.seed.manage', N'Seed the INT databases with synthetic data and clear it again (dev only; the routes 404 outside INT)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'admin.seed.manage');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'admin.seed.manage'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO
