-- 0043_delete_collaboration_permissions.sql
-- Deletes the eight dead permission codes left behind by the chat/collaboration
-- removal (feature/2.5.65): chat.view plus the seven workitem tag/priority/
-- assignment/comment codes for the details panel and the list filters. No
-- notifications.* codes exist to delete.
--
-- Child-first delete order: both dbo.AccessProfilePermission and
-- dbo.UserPermissionOverride FK Permission.PermissionID with NO CASCADE, and
-- carry live rows (the access-control drawer wrote explicit Deny rows for
-- every permission on every profile), so the Permission rows themselves must
-- go last or the delete throws a FK violation.
--
-- Naturally idempotent: once a Code's Permission row is gone, all three
-- DELETEs match zero rows on re-run.

DELETE app FROM dbo.AccessProfilePermission app
  JOIN dbo.Permission p ON p.PermissionID = app.PermissionID
 WHERE p.Code IN (N'chat.view', N'workitems.details.add.tag',
                  N'workitems.details.set.priority', N'workitems.details.assign.users',
                  N'workitems.details.add.comment', N'workitems.filter.tag',
                  N'workitems.filter.priority', N'workitems.filter.assignedUser');
GO

DELETE upo FROM dbo.UserPermissionOverride upo
  JOIN dbo.Permission p ON p.PermissionID = upo.PermissionID
 WHERE p.Code IN (N'chat.view', N'workitems.details.add.tag',
                  N'workitems.details.set.priority', N'workitems.details.assign.users',
                  N'workitems.details.add.comment', N'workitems.filter.tag',
                  N'workitems.filter.priority', N'workitems.filter.assignedUser');
GO

DELETE FROM dbo.Permission
 WHERE Code IN (N'chat.view', N'workitems.details.add.tag',
                N'workitems.details.set.priority', N'workitems.details.assign.users',
                N'workitems.details.add.comment', N'workitems.filter.tag',
                N'workitems.filter.priority', N'workitems.filter.assignedUser');
GO
