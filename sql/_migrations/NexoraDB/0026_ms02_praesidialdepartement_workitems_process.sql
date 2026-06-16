-- 0026_ms02_praesidialdepartement_workitems_process.sql
-- Workitems-list process-filter permission for the MS02 client
-- "Praesidialdepartement BS". Companion to migration 0025 (which registered the
-- DASHBOARD process); this one is for the WORKITEMS page, which parses
-- permissions of the shape 'workitems.filter.process.<client>.<process>'.
--
-- Data only (no DDL). Already applied manually on INT; this records it so fresh
-- environments (STAGING/PROD) get it too. Idempotent. Granting the permission to
-- an access profile remains a per-environment admin-UI action.
--
-- NOTE: workitems only appear in the merged list when MS02's own t_Processes has
-- a row with ClientName='sydoc' and Name='praesidialdepartement_bs' (this perm
-- only makes the process SELECTABLE; matching rows are data-dependent).
IF NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'workitems.filter.process.sydoc.praesidialdepartement_bs')
BEGIN
    INSERT INTO dbo.Permission (Code, Description)
    VALUES ('workitems.filter.process.sydoc.praesidialdepartement_bs',
            'View Praesidialdepartement BS (MS02) workitems');
END
GO
