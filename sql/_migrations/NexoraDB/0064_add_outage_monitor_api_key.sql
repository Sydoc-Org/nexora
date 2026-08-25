-- 0064_add_outage_monitor_api_key.sql
-- Monitor-only API key for the api:key outage probe (issue #201).
-- ops/outage_monitor.py sends this key as Bearer against /api/test/v1/stats/today
-- every 5 minutes, which exercises the dbo.ApiKeys lookup and the key's process
-- scope -- the half the unauthenticated api:v1 probe (401 is its pass) cannot see.
-- The raw key itself lives only in env/<ENV>.env as OUTAGE_API_KEY; only its
-- SHA-256 is stored here.
--
-- NOTE: this row lands in whichever environment the migration runs against, so
-- the same key authenticates on INT and PROD. That is deliberate (the INT
-- monitor probes with it too); revoke by flipping Enabled to 0 per environment.
--
-- Idempotent -- guarded on KeyHash, which also carries UQ_ApiKeys_KeyHash.

INSERT INTO dbo.ApiKeys (KeyHash, ClientCode, Label, ProcessList, Enabled)
SELECT '90d64b349dda6d77b95cf96c0c21700c717cddd7fd7318a82d1e2f4144ec6fa0',
       'default',
       'Prod Key for Outage Monitor not for client to use',
       'elektromaterial.02_Invoice',
       1
WHERE NOT EXISTS (
        SELECT 1 FROM dbo.ApiKeys k
        WHERE k.KeyHash = '90d64b349dda6d77b95cf96c0c21700c717cddd7fd7318a82d1e2f4144ec6fa0'
);
GO
