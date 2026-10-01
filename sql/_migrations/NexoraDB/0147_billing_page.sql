-- 0147_billing_page.sql  (#436)
-- Sydoc Billing (/billing): what was invoiced in Bexio, per Finance client,
-- next to the Finance figures of the month each invoice bills, plus the
-- invoices to unlinked contacts and everything still owed. It replaces the
-- Bexio panel that sat on Sydoc Finance (#423), which was gated by
-- finance.view.
--
-- billing.view is its own area (docs/design/permissions.md). Like
-- finance.view it reads every billing source unscoped and names every
-- client's invoices, so it is for Sydoc's own accounting and must never be
-- granted to a customer profile.
--
-- Nobody who read the invoices on Finance loses them: every access profile
-- holding finance.view gets billing.view (on INT/PROD that is Global Admin;
-- Enterprise Admin picks it up through the 0106 trigger), and every user
-- override of finance.view is mirrored, allow and deny alike.
--
-- Idempotent and self-limiting: no rows if the code or a grant is absent.

INSERT INTO dbo.Permission (Code, Description)
SELECT N'billing.view', N'View the Sydoc Billing page (what was invoiced in Bexio, next to the Finance figures it bills, and what is still owed)'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'billing.view');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID)
SELECT apf.AccessID, pb.PermissionID
FROM dbo.AccessProfilePermission apf
JOIN dbo.Permission pf ON pf.PermissionID = apf.PermissionID AND pf.Code = N'finance.view'
CROSS JOIN dbo.Permission pb
WHERE pb.Code = N'billing.view'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.AccessProfilePermission x
      WHERE x.AccessID = apf.AccessID AND x.PermissionID = pb.PermissionID
  );
GO

INSERT INTO dbo.UserPermissionOverride (UserID, PermissionID, Effect)
SELECT uof.UserID, pb.PermissionID, uof.Effect
FROM dbo.UserPermissionOverride uof
JOIN dbo.Permission pf ON pf.PermissionID = uof.PermissionID AND pf.Code = N'finance.view'
CROSS JOIN dbo.Permission pb
WHERE pb.Code = N'billing.view'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.UserPermissionOverride x
      WHERE x.UserID = uof.UserID AND x.PermissionID = pb.PermissionID
  );
GO
