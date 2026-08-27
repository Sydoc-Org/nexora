-- NEXORA_TEST seed data. Idempotent — safe to run after schema.sql.
-- Pinned bcrypt hashes (cost 12) and TOTP secrets are committed so tests are deterministic.
-- All three test users have InitReset=1 and twoFA=1, so /login goes straight to /verify_2fa.

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- Wipe any prior seed (FK-safe order)
DELETE FROM dbo.UserPermissionOverride;
DELETE FROM dbo.ActiveSessions;
DELETE FROM dbo.AccessProfilePermission;
DELETE FROM dbo.Users;
DELETE FROM dbo.Permission;
DELETE FROM dbo.AccessProfile;
DELETE FROM dbo.Organizations;
GO

DBCC CHECKIDENT('dbo.Users', RESEED, 1000);
DBCC CHECKIDENT('dbo.Permission', RESEED, 0);
DBCC CHECKIDENT('dbo.AccessProfile', RESEED, 0);
GO

-- Organization
INSERT INTO dbo.Organizations (organizationcode, Organization) VALUES
    ('TEST', 'Test Organization');
GO

-- Permission codes. The full non-generali set is seeded so the E2E subprocess
-- server (which cannot be monkeypatched like the in-process admin_all_perms
-- fixture) lets admin@test.local reach and interact with every gated page and
-- conditionally-rendered button. TestUser still receives only dashboard.view
-- and TestNoPerm none, so the permission-guard tests keep asserting 403.
INSERT INTO dbo.Permission (Code, Description) VALUES
    ('admin.view', 'View admin dashboard'),
    ('admin.users.manage', 'Manage user accounts'),
    ('admin.view.users', 'View users'),
    ('admin.interact.users.all', 'Interact with all users'),
    ('admin.create.user', 'Create user'),
    ('admin.edit.user', 'Edit user'),
    ('admin.delete.user', 'Delete user'),
    ('admin.edit.user.override', 'Edit user permission overrides'),
    ('admin.view.organizations', 'View organizations'),
    ('admin.add.organization', 'Add organization'),
    ('admin.edit.organization', 'Edit organization'),
    ('admin.delete.organization', 'Delete organization'),
    ('admin.view.accessprofiles.useroverrides', 'View access profiles and user overrides'),
    ('admin.edit.accessprofile', 'Edit access profile'),
    ('admin.view.active.sessions', 'View active sessions'),
    ('admin.view.system.logs', 'View system logs'),
    ('admin.maintenance.view', 'View maintenance banners'),
    ('admin.maintenance.edit', 'Edit maintenance banners'),
    ('admin.maintenance.bypass', 'Bypass maintenance lockout'),
    ('dashboard.view', 'View dashboard'),
    ('workitems.view', 'View workitems'),
    ('workitems.details.view', 'View workitem detail'),
    ('workitems.details.view.fields', 'View workitem fields'),
    ('workitems.details.view.images', 'View workitem images'),
    ('workitems.details.view.audit', 'View workitem audit history'),
    ('workitems.details.view.confidence', 'Workitems: view extraction confidence scores in the document viewer'),
    ('workitems.details.view.source_location', 'Workitems: view where extracted values were found on the page (source-highlight boxes; needs workitems.details.view.images)'),
    ('workitems.filter.workitemid', 'Filter workitems by id'),
    ('workitems.filter.status', 'Filter workitems by status'),
    ('workitems.filter.status.deleted', 'Workitems: show soft-deleted workitems in the status filter'),  -- migration 0044
    ('workitems.filter.stage', 'Workitems: filter by latest derived stage'),  -- migration 0048
    ('workitems.filter.datetime', 'Filter workitems by datetime'),
    ('workitems.filter.documentfields', 'Filter workitems by document fields'),
    ('workitems.filter.documentfields.sensitive', 'Workitems: see doc fields flagged sensitive'),  -- migration 0035
    ('workitems.import.workitem', 'Import workitems'),
    ('workitems.import.preparedaudit', 'Workitems: import an MS02 prepared-documents Excel (PID/Prepared) and display the matched workitems'' audit'),
    ('invoices.view', 'View invoices'),
    ('invoices.download', 'Download invoices'),
    ('invoices.filter.date', 'Filter invoices by date'),
    ('invoices.filter.status', 'Filter invoices by status'),
    ('invoices.filter.invoiceid', 'Filter invoices by id'),
    ('jd.view', 'View JD Vance page'),
    ('generali.baseservices.view', 'View Generali base services'),
    ('api.docs.view', 'View the in-app API documentation page'),  -- migration 0051
    ('admin.status.view', 'View the admin system-status page'),  -- migration 0055
    ('admin.restart', 'Restart the dev server from the admin overview (dev-only)'),  -- migration 0059
    ('reporting.view', 'Access the Reporting page'),
    ('reporting.source.backlog_history', 'Reporting: use the Backlog History source'),  -- migration 0053
    ('reporting.source.docprocessing', 'Reporting: use the Document Processing source'),
    ('reporting.export', 'Reporting: export reports to Excel'),
    ('reporting.sql.run', 'Reporting: run live read-only SQL (sandboxed)'),
    ('reporting.sql.target.octopus', 'Reporting: target the Octopus runtime DB in the live-SQL sandbox'),
    ('reporting.admin.sources', 'Reporting: manage the data-source registry'),
    ('reporting.sources.schema', 'Reporting: browse a source database''s tables, columns and relationships'),  -- migration 0079
    ('reporting.semantic.admin', 'Reporting: manage the canonical metrics registry'),
    ('reporting.source.generali.pdqm', 'Reporting: use the Generali PDQM Report source'),
    ('reporting.source.workitems', 'Reporting: use the Workitems (Octopus) source'),
    ('reporting.schedule', 'Reporting: schedule a report to run and be emailed'),
    ('reporting.ai.use', 'Reporting: use the AI assistant (NL questions)'),
    ('reporting.ai.sql', 'Reporting: AI may emit live SQL (advanced)'),
    ('reporting.ai.explain', 'Reporting: see AI explanation on results'),
    -- Mirrors sql/_migrations/NexoraDB/0015_seed_reporting_ai_explain_data.sql
    -- (the data-egress grant for the agentic tool loop / Task 13 captions).
    ('reporting.ai.explain_data', 'Reporting: let the AI assistant run read-only queries and explain the actual result numbers (data egress to the model; needs reporting.sql.run)');
GO

-- Access profiles
INSERT INTO dbo.AccessProfile (Name, Description) VALUES
    ('TestAdmin',  'Test admin profile — has admin.view + admin.users.manage + dashboard.view'),
    ('TestUser',   'Test user profile — has dashboard.view only'),
    ('TestNoPerm', 'Test no-permission profile');
GO

-- Wire permissions to access profiles.
-- TestAdmin gets EVERY permission (omnipotent test admin) so E2E flows can
-- reach and exercise every page. TestUser keeps dashboard.view only.
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, p.PermissionID, 'A'
FROM dbo.AccessProfile ap, dbo.Permission p
WHERE ap.Name = 'TestAdmin';

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, p.PermissionID, 'A'
FROM dbo.AccessProfile ap, dbo.Permission p
WHERE ap.Name = 'TestUser' AND p.Code = 'dashboard.view';
-- TestNoPerm gets no rows
GO

-- Test users.
-- Password = Test1234! (bcrypt cost 12, regenerate with:
--   python -c "import bcrypt; print(bcrypt.hashpw(b'Test1234!', bcrypt.gensalt(12)).decode())")
-- TOTP secrets match tests/conftest.py TOTP_SECRETS dict exactly.
INSERT INTO dbo.Users (username, password, Fullname, Email, accessid, organizationCode, InitReset, twoFA, twoFASecret, locale)
VALUES
    ('admin@test.local',
     '$2b$12$yMKpG3tUGtM6/fmd36giJ.VY5DHY5zRU4twHKfjQ5TsR.3kn7UxW.',
     'Test Admin',
     'admin@test.local',
     (SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestAdmin'),
     'TEST', 1, 1, 'JBSWY3DPEHPK3PXP', 'en'),

    ('user@test.local',
     '$2b$12$D7op.8v3zbknmjjmS//FTuGV0THtWdlF8OU6goyKsNlA5sJ0HC0a6',
     'Test User',
     'user@test.local',
     (SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestUser'),
     'TEST', 1, 1, 'KRSXG5CTMVRXEZLU', 'en'),

    ('noperm@test.local',
     '$2b$12$eYbecob1wu3hXEa43ji0BuLYyr1yLCAXNGMguI.NdMFVzIOXq6w6W',
     'Test NoPerm',
     'noperm@test.local',
     (SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestNoPerm'),
     'TEST', 1, 1, 'MFRGGZDFMZTWQ2LK', 'en'),

    -- TestAdmin profile (every permission) minus reporting.ai.explain_data via
    -- the per-user override below -- lets Task 13's e2e "unaffected without
    -- the perm" spot-check exercise a fully-working reporting page/Advanced
    -- tab that simply never shows the caption slot. Same password hash as
    -- admin@test.local (same Test1234! plaintext -- bcrypt hashes just don't
    -- match across independent generations).
    ('noai@test.local',
     '$2b$12$yMKpG3tUGtM6/fmd36giJ.VY5DHY5zRU4twHKfjQ5TsR.3kn7UxW.',
     'Test NoAI',
     'noai@test.local',
     (SELECT AccessID FROM dbo.AccessProfile WHERE Name = 'TestAdmin'),
     'TEST', 1, 1, 'GEZDGNBVGY3TQOJQ', 'en');
GO

-- Deny reporting.ai.explain_data for noai@test.local only (a per-user
-- override beats the TestAdmin access-profile grant -- see
-- dbo.fnUserHasPermission). Every other TestAdmin permission stays intact.
INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT u.userID, p.PermissionID, 'D'
FROM dbo.Users u, dbo.Permission p
WHERE u.username = 'noai@test.local' AND p.Code = 'reporting.ai.explain_data';
GO

-- Curated 'table' reporting sources (mirrors 0011_seed_generali_workitems_sources.sql)
-- so the registry/listing can be exercised in TEST. Running them needs the live
-- Generali/Octopus DBs, so the e2e/integration tests only assert they register.
IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'generali_pdqm')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'generali_pdqm', 'curated', 'Generali — PDQM Report',
    'reporting.source.generali.pdqm', 'generali', 'table', 'dbo.PDQMReport',
    N'[{"field":"ForDate","label":"Date","type":"date","filterable":true,"sortable":true},
       {"field":"ParentCategory","label":"Parent category","type":"string","filterable":true,"sortable":true},
       {"field":"Quantity","label":"Quantity","type":"number","filterable":true,"sortable":true}]',
    1, 20);
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'workitems')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'workitems', 'curated', 'Workitems (Octopus)',
    'reporting.source.workitems', 'octopus', 'table', 'dbo.t_Documents',
    N'[{"field":"WorkItemIdentifier","label":"Workitem ID","type":"string","filterable":true,"sortable":true},
       {"field":"DocumentName","label":"Document name","type":"string","filterable":true,"sortable":true},
       {"field":"DocumentRevision","label":"Revision","type":"number","filterable":true,"sortable":true}]',
    1, 30);
GO
