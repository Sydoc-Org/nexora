/* ============================================================================
   provision-reporting-ro-logins.sql

   One-shot provisioning of the two READ-ONLY (db_datareader) SQL logins the
   Reporting page needs for its live SQL sandbox, scheduled reports, and the
   AI assistant's schema grounding:

     | Target     | Database              | env vars (env/INT.env + env/PROD.env)         |
     |------------|-----------------------|-----------------------------------------------|
     | Statistics | $(StatisticsDb)       | DB_REPORTING_RO_USER  / DB_REPORTING_RO_PWD   |
     | Octopus    | $(OctopusDb)          | DB_REPORTING_OCTO_RO_USER / DB_REPORTING_OCTO_RO_PWD |

   Both databases live on DB_SERVER_PRD (see nx_lib/db.py: get_ro_db_url defaults
   the server to cfg.DB_SERVER_PRD). Run this ONCE, connected to DB_SERVER_PRD,
   as a login with ALTER ANY LOGIN (server) + db_owner on both databases
   (typically sysadmin). It is idempotent — re-running is safe, and re-running
   with a different password ROTATES the login's password (the server is reset
   to the :setvar value via ALTER LOGIN). So the server always matches the
   DB_REPORTING_*_RO_PWD you put in the env files. Run this on EACH SQL server
   the env points at (INT and PROD `DB_SERVER_PRD` may be different hosts).

   ----------------------------------------------------------------------------
   HOW TO RUN (SSMS)
   ----------------------------------------------------------------------------
   1. Open this file in SSMS connected to DB_SERVER_PRD.
   2. Enable SQLCMD Mode:  Query menu -> "SQLCMD Mode".
   3. Edit the six :setvar lines below — set the real database names and pick
      STRONG passwords for the two logins. Do NOT commit the filled-in copy.
   4. Execute (F5).
   5. Put the same login names + passwords into BOTH env/INT.env and
      env/PROD.env (INT and PROD reference the same DB_SERVER_PRD logins):

        DB_REPORTING_RO_USER=<StatisticsRoLogin>
        DB_REPORTING_RO_PWD=<StatisticsRoPwd>
        DB_REPORTING_OCTO_RO_USER=<OctopusRoLogin>
        DB_REPORTING_OCTO_RO_PWD=<OctopusRoPwd>

   6. Restart nexora so config.py reloads the env (bin\nx.ps1 -r). Until the env
      vars are present, each target's RO engine stays None and a run against it
      returns 503 "SQL source is not configured".

   NOTE: this script is intentionally NOT a sql/_migrations/ migration. It runs
   against StatisticsDB / OctopusDB, which are vendor/runtime surfaces we do not
   track (see CLAUDE.md "Databases"). It carries secrets (passwords) only in the
   owner's local edited copy, never in the repo.
   ============================================================================ */

-- ====== EDIT THESE SIX VALUES (SQLCMD Mode required) ========================
:setvar StatisticsDb      "sydoc_stat"
:setvar StatisticsRoLogin "nexora_reporting_ro"
:setvar StatisticsRoPwd   "CHANGE-ME-strong-password-1"

:setvar OctopusDb         "REPLACE_WITH_OCTOPUS_DB_NAME"
:setvar OctopusRoLogin    "nexora_reporting_octo_ro"
:setvar OctopusRoPwd      "CHANGE-ME-strong-password-2"
-- ===========================================================================

SET NOCOUNT ON;
GO

/* --- 1. Server-level logins (idempotent; re-running ROTATES the password) -- */
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'$(StatisticsRoLogin)')
BEGIN
    CREATE LOGIN [$(StatisticsRoLogin)]
        WITH PASSWORD = N'$(StatisticsRoPwd)',
             CHECK_POLICY = ON,
             DEFAULT_DATABASE = [$(StatisticsDb)];
    PRINT 'Created login $(StatisticsRoLogin)';
END
ELSE
BEGIN
    -- Login already exists: reset its password to the :setvar value so the
    -- server always matches DB_REPORTING_RO_PWD (re-run to rotate).
    ALTER LOGIN [$(StatisticsRoLogin)] WITH PASSWORD = N'$(StatisticsRoPwd)';
    PRINT 'Login $(StatisticsRoLogin) already existed - password reset to the :setvar value';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'$(OctopusRoLogin)')
BEGIN
    CREATE LOGIN [$(OctopusRoLogin)]
        WITH PASSWORD = N'$(OctopusRoPwd)',
             CHECK_POLICY = ON,
             DEFAULT_DATABASE = [$(OctopusDb)];
    PRINT 'Created login $(OctopusRoLogin)';
END
ELSE
BEGIN
    -- Login already exists: reset its password to the :setvar value so the
    -- server always matches DB_REPORTING_OCTO_RO_PWD (re-run to rotate).
    ALTER LOGIN [$(OctopusRoLogin)] WITH PASSWORD = N'$(OctopusRoPwd)';
    PRINT 'Login $(OctopusRoLogin) already existed - password reset to the :setvar value';
END
GO

/* --- 2. Statistics DB: user + db_datareader (read-only) -------------------- */
USE [$(StatisticsDb)];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(StatisticsRoLogin)')
BEGIN
    CREATE USER [$(StatisticsRoLogin)] FOR LOGIN [$(StatisticsRoLogin)];
    PRINT 'Created user $(StatisticsRoLogin) in $(StatisticsDb)';
END
ELSE
    PRINT 'User $(StatisticsRoLogin) already exists in $(StatisticsDb)';
GO
ALTER ROLE db_datareader ADD MEMBER [$(StatisticsRoLogin)];   -- read-only; safe to repeat
GO

/* --- 3. Octopus DB: user + db_datareader (read-only) ----------------------- */
USE [$(OctopusDb)];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(OctopusRoLogin)')
BEGIN
    CREATE USER [$(OctopusRoLogin)] FOR LOGIN [$(OctopusRoLogin)];
    PRINT 'Created user $(OctopusRoLogin) in $(OctopusDb)';
END
ELSE
    PRINT 'User $(OctopusRoLogin) already exists in $(OctopusDb)';
GO
ALTER ROLE db_datareader ADD MEMBER [$(OctopusRoLogin)];      -- read-only; safe to repeat
GO

PRINT 'Done. Now set the four DB_REPORTING_*_RO_* vars in env/INT.env + env/PROD.env and restart nexora.';
GO
