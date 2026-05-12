USE [nexora]
GO
ALTER TABLE [dbo].[Chat_Conversations] DROP CONSTRAINT [DF__Chat_Conv__LastM__55BFB948]
GO
ALTER TABLE [dbo].[Chat_Conversations] DROP CONSTRAINT [DF__Chat_Conv__Creat__54CB950F]
GO
DROP TABLE [dbo].[Chat_Conversations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Chat_Conversations](
	[ConversationID] [int] IDENTITY(1,1) NOT NULL,
	[CreatedAt] [datetime] NULL,
	[LastMessageAt] [datetime] NULL,
PRIMARY KEY CLUSTERED 
(
	[ConversationID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Chat_Conversations] ADD  DEFAULT (getdate()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[Chat_Conversations] ADD  DEFAULT (getdate()) FOR [LastMessageAt]
GO
