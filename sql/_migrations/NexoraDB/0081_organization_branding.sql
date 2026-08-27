-- 0081: white-label branding columns on dbo.Organizations (#98 phase 4, PHASE C).
-- Branding attaches to the Organization (the customer -- PRVR, LKTR, ...), never to
-- ClientCode (the runtime source -- default, ms02): those are different axes, see
-- docs/superpowers/specs/2026-08-27-white-label-admin-ui-design.md "two axes" section.
--
-- All three columns are nullable -- that's the whole point: every existing org row
-- keeps today's Nexora branding until an admin opts it into custom branding.
-- nx_lib/branding.py reads these into a cached registry.

IF COL_LENGTH('dbo.Organizations', 'BrandName') IS NULL
ALTER TABLE dbo.Organizations ADD BrandName NVARCHAR(100) NULL;
GO

IF COL_LENGTH('dbo.Organizations', 'BrandAccentHex') IS NULL
ALTER TABLE dbo.Organizations ADD BrandAccentHex NVARCHAR(7) NULL;
GO

IF COL_LENGTH('dbo.Organizations', 'BrandLogoFile') IS NULL
ALTER TABLE dbo.Organizations ADD BrandLogoFile NVARCHAR(255) NULL;
GO
