-- 0079_add_reporting_source_schema_permission.sql
-- New grantable permission for the Console's source visualizer: clicking a
-- card in the Reporting rail opens a slide-over with that database's tables,
-- columns and foreign keys (list + ER diagram), served by
-- GET /api/reporting/sources/<id>/schema.
--   reporting.sources.schema -- browse the schema of a source's database
-- The route additionally requires the source's own permission, so this grant
-- never widens which databases a user can reach -- only how much of the one
-- they already read they get to see.
-- Seeded Effect 'A' to every access profile that already grants admin.view.
-- Idempotent. Mirrors migrations 0051 / 0059.

INSERT INTO dbo.Permission (Code, Description)
SELECT 'reporting.sources.schema',
       'Browse the tables, columns and relationships of a reporting source''s database'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = 'reporting.sources.schema');
GO

INSERT INTO dbo.AccessProfilePermission (AccessID, PermissionID, Effect)
SELECT ap.AccessID, np.PermissionID, 'A'
FROM dbo.AccessProfilePermission ap
JOIN dbo.Permission admin_p ON admin_p.PermissionID = ap.PermissionID
                            AND admin_p.Code = 'admin.view' AND ap.Effect = 'A'
CROSS JOIN dbo.Permission np
WHERE np.Code = 'reporting.sources.schema'
  AND NOT EXISTS (
        SELECT 1 FROM dbo.AccessProfilePermission x
        WHERE x.AccessID = ap.AccessID AND x.PermissionID = np.PermissionID
  );
GO
