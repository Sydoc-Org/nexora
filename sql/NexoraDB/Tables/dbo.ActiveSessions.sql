USE [nexora]
GO
ALTER TABLE [dbo].[ActiveSessions] DROP CONSTRAINT [DF_ActiveSessions_LastSeenAt]
GO
ALTER TABLE [dbo].[ActiveSessions] DROP CONSTRAINT [DF_ActiveSessions_CreatedAt]
GO
DROP INDEX [IX_ActiveSessions_UserID] ON [dbo].[ActiveSessions]
GO
DROP INDEX [IX_ActiveSessions_LastSeenAt] ON [dbo].[ActiveSessions]
GO
DROP TABLE [dbo].[ActiveSessions]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ActiveSessions](
	[SessionID] [nvarchar](64) NOT NULL,
	[UserID] [int] NOT NULL,
	[CreatedAt] [datetime] NOT NULL,
	[IPAddress] [nvarchar](45) NULL,
	[LastSeenAt] [datetime] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[SessionID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ActiveSessions_LastSeenAt] ON [dbo].[ActiveSessions]
(
	[LastSeenAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ActiveSessions_UserID] ON [dbo].[ActiveSessions]
(
	[UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ActiveSessions] ADD  CONSTRAINT [DF_ActiveSessions_CreatedAt]  DEFAULT (getdate()) FOR [CreatedAt]
GO
ALTER TABLE [dbo].[ActiveSessions] ADD  CONSTRAINT [DF_ActiveSessions_LastSeenAt]  DEFAULT (getdate()) FOR [LastSeenAt]
GO
