-- 0042: chat/collaboration/notification removal (feature/2.5.65).
-- Renames the nine dead tables with a decapitated_ prefix (data preserved,
-- reversible) and drops their FKs to dbo.Users so user deletion keeps working
-- after admin_delete_user lost its collaboration child-deletes.
--
-- Idempotent (survives the pre-commit hook re-applying it):
--   * FK-drop batch keys on the ORIGINAL table names, so once the tables are
--     renamed the SELECT matches nothing and the batch is a no-op.
--   * Each sp_rename is guarded by OBJECT_ID(old) IS NOT NULL
--     AND OBJECT_ID(new) IS NULL.
--
-- sp_rename's second argument MUST be the BARE new name (never schema-qualified,
-- e.g. N'decapitated_Chat_Conversations', not N'dbo.decapitated_...').
-- FK names are auto-generated and differ per environment, hence the dynamic
-- sys.foreign_keys lookup -- never hardcode a constraint name.
--
-- Intra-group FKs (Chat_Messages->Chat_Conversations,
-- Chat_Participants->Chat_Conversations, Workitem_Tags->Tags) are deliberately
-- NOT dropped: both sides die together in this migration and the FK follows the
-- rename by object_id. Only the seven tables carrying FKs to dbo.Users are
-- touched (Chat_Conversations and Workitem_Tags carry none).
DECLARE @sql nvarchar(max) = N'';
SELECT @sql = @sql + N'ALTER TABLE dbo.' + QUOTENAME(OBJECT_NAME(fk.parent_object_id))
             + N' DROP CONSTRAINT ' + QUOTENAME(fk.name) + N';'
FROM sys.foreign_keys fk
WHERE fk.referenced_object_id = OBJECT_ID(N'dbo.Users')
  AND OBJECT_NAME(fk.parent_object_id) IN
      (N'Chat_Messages', N'Chat_Participants', N'Tags', N'Workitem_Comments',
       N'Comment_Mentions', N'Notifications', N'Workitem_Metadata');
IF LEN(@sql) > 0 EXEC sp_executesql @sql;
GO
IF OBJECT_ID(N'dbo.Chat_Conversations', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Chat_Conversations', N'U') IS NULL
    EXEC sp_rename N'dbo.Chat_Conversations', N'decapitated_Chat_Conversations';
GO
IF OBJECT_ID(N'dbo.Chat_Messages', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Chat_Messages', N'U') IS NULL
    EXEC sp_rename N'dbo.Chat_Messages', N'decapitated_Chat_Messages';
GO
IF OBJECT_ID(N'dbo.Chat_Participants', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Chat_Participants', N'U') IS NULL
    EXEC sp_rename N'dbo.Chat_Participants', N'decapitated_Chat_Participants';
GO
IF OBJECT_ID(N'dbo.Tags', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Tags', N'U') IS NULL
    EXEC sp_rename N'dbo.Tags', N'decapitated_Tags';
GO
IF OBJECT_ID(N'dbo.Workitem_Tags', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Workitem_Tags', N'U') IS NULL
    EXEC sp_rename N'dbo.Workitem_Tags', N'decapitated_Workitem_Tags';
GO
IF OBJECT_ID(N'dbo.Workitem_Comments', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Workitem_Comments', N'U') IS NULL
    EXEC sp_rename N'dbo.Workitem_Comments', N'decapitated_Workitem_Comments';
GO
IF OBJECT_ID(N'dbo.Comment_Mentions', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Comment_Mentions', N'U') IS NULL
    EXEC sp_rename N'dbo.Comment_Mentions', N'decapitated_Comment_Mentions';
GO
IF OBJECT_ID(N'dbo.Notifications', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Notifications', N'U') IS NULL
    EXEC sp_rename N'dbo.Notifications', N'decapitated_Notifications';
GO
IF OBJECT_ID(N'dbo.Workitem_Metadata', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_Workitem_Metadata', N'U') IS NULL
    EXEC sp_rename N'dbo.Workitem_Metadata', N'decapitated_Workitem_Metadata';
GO
