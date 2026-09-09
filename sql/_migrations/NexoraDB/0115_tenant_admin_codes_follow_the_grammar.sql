-- 0115: admin.view.tenants / admin.edit.tenants (0095) follow the #238 grammar.
-- 0095 was written before 0088 renamed the catalogue; grants ride on PermissionID,
-- so the rename costs nobody anything. Idempotent.
UPDATE dbo.Permission SET Code = 'admin.tenants.view'
 WHERE Code = 'admin.view.tenants'
   AND NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'admin.tenants.view');
UPDATE dbo.Permission SET Code = 'admin.tenants.edit'
 WHERE Code = 'admin.edit.tenants'
   AND NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = 'admin.tenants.edit');
GO
