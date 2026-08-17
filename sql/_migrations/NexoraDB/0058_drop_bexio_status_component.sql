-- 0058: retire the bexio:api status component (#177).
-- The Bexio probe went with the archived invoices page: nothing in the app
-- calls Bexio any more, so ops/outage_monitor.py no longer emits bexio:api and
-- nx --doctor no longer checks it. The admin status page renders every row in
-- dbo.StatusComponents, so without this the component would sit on the page
-- forever, frozen at whatever the last poll wrote.
--
-- Any still-open incident is closed rather than deleted -- an outage that
-- really happened stays in the 30-day history (it ages out on its own).
--
-- Idempotent: both statements are set-based and match nothing on a re-run.
--
-- dbo.StatusIncidents carries the filtered index UX_StatusIncidents_Open, and
-- any DML against a table with one requires QUOTED_IDENTIFIER ON -- which
-- sqlcmd does not default to. Without this SET the UPDATE fails with Msg 1934
-- (same trap 0055 hit when it created the index).
SET QUOTED_IDENTIFIER ON;
GO
UPDATE dbo.StatusIncidents
   SET EndedAt = SYSDATETIME()
 WHERE ComponentKey = N'bexio:api' AND EndedAt IS NULL;
GO
DELETE FROM dbo.StatusComponents WHERE ComponentKey = N'bexio:api';
GO

-- This migration was briefly numbered 0057 and applied to INT under that name
-- before a parallel branch claimed 0057 for dbo.WorkitemFilterViews. Renumbering
-- leaves a SchemaMigrations row pointing at a file that no longer exists; drop
-- it so the ledger matches the folder. No-op everywhere else.
DELETE FROM dbo.SchemaMigrations WHERE FileName = N'0057_drop_bexio_status_component.sql';
GO
