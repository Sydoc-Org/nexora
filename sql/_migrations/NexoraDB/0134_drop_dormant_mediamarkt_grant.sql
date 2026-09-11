-- 0134_drop_dormant_mediamarkt_grant.sql
-- Remove reporting.source.mediamarkt_batches.use from the 'Sydoc User' profile
-- (#332).
--
-- WHY
-- That profile has 8 users and does NOT hold reporting.view, so every reporting
-- route already refuses it and the grant does nothing today. It is a trap rather
-- than a leak: the day somebody adds reporting.view to 'Sydoc User' -- thinking
-- about reporting access, not about MediaMarkt -- those 8 users silently gain a
-- customer's batch figures in the same click.
--
-- The `table` provider applies no row scoping, so a source permission is the
-- whole gate. There is no second check to catch a grant nobody meant to make,
-- which is exactly why a half-finished one should not be left lying around.
--
-- WHERE IT CAME FROM
-- Not from a migration. 0126 created the permission and registered the source
-- but granted it to nobody; this pairing was made by hand in the admin UI. INT
-- does not have it -- there, only Enterprise Admin holds the source -- so this
-- migration is a no-op on INT and a correction on PROD. That divergence is the
-- reason it is being fixed in a migration rather than by another click: this
-- way both environments end up saying the same thing.
--
-- NOT TOUCHED
-- The same permission is also held on PROD by Global Admin and Sydoc Supervisor.
-- Both hold reporting.view, both are internal SYDOC staff, and both grants are
-- intentional. Only the dormant one goes.
--
-- Idempotent: a DELETE that matches nothing is a no-op, and re-granting the
-- permission deliberately later is unaffected (migrations run once).

DELETE app
FROM dbo.AccessProfilePermission app
JOIN dbo.AccessProfile ap ON ap.AccessID = app.AccessID
JOIN dbo.Permission p ON p.PermissionID = app.PermissionID
WHERE ap.Name = N'Sydoc User'
  AND p.Code = N'reporting.source.mediamarkt_batches.use';
GO
