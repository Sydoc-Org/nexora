USE [nexora]
GO
ALTER TABLE [dbo].[decapitated_Chat_Participants] DROP CONSTRAINT [FK__Chat_Part__Conve__589C25F3]
GO
DROP INDEX [IX_Chat_Participants_User] ON [dbo].[decapitated_Chat_Participants]
GO
DROP TABLE [dbo].[decapitated_Chat_Participants]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[decapitated_Chat_Participants](
	[ConversationID] [int] NOT NULL,
	[UserID] [int] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[ConversationID] ASC,
	[UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Chat_Participants_User] ON [dbo].[decapitated_Chat_Participants]
(
	[UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[decapitated_Chat_Participants]  WITH CHECK ADD FOREIGN KEY([ConversationID])
REFERENCES [dbo].[decapitated_Chat_Conversations] ([ConversationID])
ON DELETE CASCADE
GO
