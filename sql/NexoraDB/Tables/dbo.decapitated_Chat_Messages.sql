USE [nexora]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages] DROP CONSTRAINT [FK__Chat_Mess__Conve__5E54FF49]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages] DROP CONSTRAINT [DF__Chat_Mess__IsRea__5D60DB10]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages] DROP CONSTRAINT [DF__Chat_Mess__Times__5C6CB6D7]
GO
DROP INDEX [IX_Chat_Messages_Conversation] ON [dbo].[decapitated_Chat_Messages]
GO
DROP TABLE [dbo].[decapitated_Chat_Messages]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[decapitated_Chat_Messages](
	[MessageID] [int] IDENTITY(1,1) NOT NULL,
	[ConversationID] [int] NULL,
	[SenderID] [int] NULL,
	[MessageText] [nvarchar](max) NULL,
	[Timestamp] [datetime] NULL,
	[IsRead] [bit] NULL,
PRIMARY KEY CLUSTERED 
(
	[MessageID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_Chat_Messages_Conversation] ON [dbo].[decapitated_Chat_Messages]
(
	[ConversationID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages] ADD  DEFAULT ((0)) FOR [IsRead]
GO
ALTER TABLE [dbo].[decapitated_Chat_Messages]  WITH CHECK ADD FOREIGN KEY([ConversationID])
REFERENCES [dbo].[decapitated_Chat_Conversations] ([ConversationID])
ON DELETE CASCADE
GO
