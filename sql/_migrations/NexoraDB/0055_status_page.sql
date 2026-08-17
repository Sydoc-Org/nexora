-- 0055_status_page.sql
-- REF #167: admin status page (operational / degraded / outage / maintenance).
--
-- The outage monitor from #166 keeps its working state in var/outage-state.json
-- on purpose -- it has to keep alerting when NexoraDB is the thing that is down.
-- These two tables are the *reporting* mirror it writes after each run, and the
-- only thing the status page reads. A future public status page living outside
-- the app (see the #167 notes) consumes the same two tables.
--
--   StatusComponents -- one row per fixed component, current state, overwritten
--                       every monitor run.
--   StatusIncidents  -- append-only outage log; EndedAt NULL means still open.
--                       Log-storm components only ever appear here, never in
--                       StatusComponents: their keys are content hashes, so a
--                       permanent row per error signature ever seen would turn
--                       the component grid into a junk drawer.
--
-- Also seeds the admin.status.view permission. Idempotent. Mirrors 0051.

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'StatusComponents' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.StatusComponents (
        ComponentKey  NVARCHAR(200)  NOT NULL CONSTRAINT PK_StatusComponents PRIMARY KEY,
        ComponentName NVARCHAR(200)  NOT NULL,
        State         VARCHAR(20)    NOT NULL,
        Detail        NVARCHAR(1000) NULL,
        FirstSeenAt   DATETIME2(0)   NOT NULL,
        LastCheckedAt DATETIME2(0)   NOT NULL,
        LastOkAt      DATETIME2(0)   NULL,
        CONSTRAINT CK_StatusComponents_State
            CHECK (State IN ('operational', 'degraded', 'outage'))
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'StatusIncidents' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.StatusIncidents (
        ID            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_StatusIncidents PRIMARY KEY,
        ComponentKey  NVARCHAR(200)  NOT NULL,
        ComponentName NVARCHAR(200)  NOT NULL,
        StartedAt     DATETIME2(0)   NOT NULL,
        EndedAt       DATETIME2(0)   NULL,
        Detail        NVARCHAR(1000) NULL,
        Excerpt       NVARCHAR(MAX)  NULL
    );
END
GO

-- History reads are always "this component, newest first" or "everything in the
-- last N days"; both are covered by leading on StartedAt.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_StatusIncidents_StartedAt')
    CREATE INDEX IX_StatusIncidents_StartedAt
        ON dbo.StatusIncidents (StartedAt DESC) INCLUDE (ComponentKey, EndedAt);
GO

-- One open incident per component, enforced in the DB rather than trusting the
-- monitor's hysteresis: a half-written run must not be able to leave two.
-- A filtered index requires QUOTED_IDENTIFIER ON, which sqlcmd does not default
-- to -- without this SET the batch fails with Msg 1934.
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_StatusIncidents_Open')
    CREATE UNIQUE INDEX UX_StatusIncidents_Open
        ON dbo.StatusIncidents (ComponentKey) WHERE EndedAt IS NULL;
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT 'admin.status.view',
       'View the system status page (/admin/status): component health and incident history'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'admin.status.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'admin.status.view'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
