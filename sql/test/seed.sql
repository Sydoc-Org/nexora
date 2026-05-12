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

-- Permission codes used by round-1 tests
INSERT INTO dbo.Permission (Code, Description) VALUES
    ('admin.view', 'View admin dashboard'),
    ('admin.users.manage', 'Manage user accounts'),
    ('dashboard.view', 'View dashboard');
GO

-- Access profiles
INSERT INTO dbo.AccessProfile (Name, Description) VALUES
    ('TestAdmin',  'Test admin profile — has admin.view + admin.users.manage + dashboard.view'),
    ('TestUser',   'Test user profile — has dashboard.view only'),
    ('TestNoPerm', 'Test no-permission profile');
GO

-- Wire permissions to access profiles
INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, p.PermissionID, 'A'
FROM dbo.AccessProfile ap, dbo.Permission p
WHERE ap.Name = 'TestAdmin' AND p.Code IN ('admin.view', 'admin.users.manage', 'dashboard.view');

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
     'TEST', 1, 1, 'MFRGGZDFMZTWQ2LK', 'en');
GO
