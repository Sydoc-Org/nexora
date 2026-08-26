-- 0072: drop the decapitated_* tables for good (#98).
-- 0042 (chat/collaboration/notifications) and 0056 (client invoices) renamed
-- these dead tables with a decapitated_ prefix instead of dropping them, as a
-- reversible safety net. Nothing has read them since: zero live code
-- references (verified 2026-08-26 — the only textual hit was the archived,
-- never-registered views/invoices.py, deleted in the same commit), and their
-- only remaining FKs point at each other (FKs to dbo.Users were already
-- severed by 0042). This migration burns the safety net: the data is gone.
--
-- Idempotent: every DROP is guarded, so the pre-commit hook can re-apply it.
-- Order matters only for the FK children: Chat_Messages / Chat_Participants
-- reference Chat_Conversations, Workitem_Tags references Tags.

IF OBJECT_ID('dbo.decapitated_Chat_Messages', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Chat_Messages;
IF OBJECT_ID('dbo.decapitated_Chat_Participants', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Chat_Participants;
IF OBJECT_ID('dbo.decapitated_Chat_Conversations', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Chat_Conversations;
GO

IF OBJECT_ID('dbo.decapitated_Workitem_Tags', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Workitem_Tags;
IF OBJECT_ID('dbo.decapitated_Tags', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Tags;
GO

IF OBJECT_ID('dbo.decapitated_Comment_Mentions', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Comment_Mentions;
IF OBJECT_ID('dbo.decapitated_Workitem_Comments', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Workitem_Comments;
IF OBJECT_ID('dbo.decapitated_Notifications', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Notifications;
IF OBJECT_ID('dbo.decapitated_Workitem_Metadata', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_Workitem_Metadata;
IF OBJECT_ID('dbo.decapitated_ClientInvoices', 'U') IS NOT NULL
    DROP TABLE dbo.decapitated_ClientInvoices;
GO
