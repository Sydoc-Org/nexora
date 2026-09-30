-- 0140_bps_page.sql  (#415)
-- The Sydoc BPS page (/bps): every hour booked in the BPS timetool
-- (SYDOC_Statistik.dbo.BPS_ProjectReport, 0124), drilled down by task,
-- customer and person, down to the single booking and its comment.
--
-- bps.view is its own area. The page reads the bps_projects source through the
-- generic 'table' provider, which applies no row scoping, and shows every
-- employee's bookings by name -- internal HR-adjacent data. It is for Sydoc's
-- own management and must never be granted to a customer profile.
-- Global Admin gets it here (a hand-picked profile, see 0136/0138);
-- Enterprise Admin picks it up through the 0106 trigger. Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'bps.view', N'View the Sydoc BPS page (all hours booked in the BPS timetool, per task, customer and person)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'bps.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT ap.AccessID, p.PermissionID
FROM dbo.AccessProfile ap
CROSS JOIN dbo.Permission p
WHERE ap.Name = N'Global Admin'
  AND p.Code = N'bps.view'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = ap.AccessID AND x.PermissionID = p.PermissionID
  );
GO
