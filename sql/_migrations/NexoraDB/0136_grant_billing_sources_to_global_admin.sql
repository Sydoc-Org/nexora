-- 0136_grant_billing_sources_to_global_admin.sql
-- Grant the six billing sources from 0130-0135 to the 'Global Admin' profile
-- (#329).
--
-- WHY THIS IS NEEDED AT ALL
-- 0130-0135 create each source's permission but grant it to nobody. Enterprise
-- Admin still ends up holding them because that profile holds *every*
-- permission -- 136 of 136 on PROD -- so it picks up anything new for free.
-- Global Admin does not: it carries a hand-picked subset and was missing all
-- six, along with xpert_stats, bucherer_easytax, frigemo, bps_projects and most
-- of the generali sources. So the sources deployed correctly and were simply
-- invisible to the one person who needed to check them.
--
-- WHY GLOBAL ADMIN AND NOBODY ELSE
-- It is internal SYDOC staff at rank 90, one user, and it already holds
-- reporting.view plus reporting.sql.run -- someone with the SQL sandbox can
-- already read these tables directly, so this grants no reach that profile did
-- not effectively have. It does not touch any customer-facing profile: those
-- hold no reporting.view at all, and the row-scoping caveat on #332 still
-- applies to anyone who later wants a customer to see their own figures.
--
-- Deliberately a migration and not a click in the admin UI. The dormant
-- MediaMarkt grant on #332 exists precisely because somebody did it by hand:
-- INT and PROD disagree, and there is no record of who or why.
--
-- Idempotent, and self-limiting -- it inserts nothing if either the profile or
-- the permission is absent, so a fresh INT without the profile is a no-op
-- rather than an error.

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code IN (
      N'reporting.source.em_invoice.use',
      N'reporting.source.compass_invoice.use',
      N'reporting.source.privera_invoice.use',
      N'reporting.source.privera_nachsendungen.use',
      N'reporting.source.privera_neuzugaenge.use',
      N'reporting.source.privera_posteingang.use'
  )
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO
