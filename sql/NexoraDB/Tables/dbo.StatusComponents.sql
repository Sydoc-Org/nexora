USE [nexora]
GO
ALTER TABLE [dbo].[StatusComponents] DROP CONSTRAINT [CK_StatusComponents_State]
GO
DROP TABLE [dbo].[StatusComponents]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[StatusComponents](
	[ComponentKey] [nvarchar](200) NOT NULL,
	[ComponentName] [nvarchar](200) NOT NULL,
	[State] [varchar](20) NOT NULL,
	[Detail] [nvarchar](1000) NULL,
	[FirstSeenAt] [datetime2](0) NOT NULL,
	[LastCheckedAt] [datetime2](0) NOT NULL,
	[LastOkAt] [datetime2](0) NULL,
 CONSTRAINT [PK_StatusComponents] PRIMARY KEY CLUSTERED 
(
	[ComponentKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[StatusComponents]  WITH CHECK ADD  CONSTRAINT [CK_StatusComponents_State] CHECK  (([State]='outage' OR [State]='degraded' OR [State]='operational'))
GO
ALTER TABLE [dbo].[StatusComponents] CHECK CONSTRAINT [CK_StatusComponents_State]
GO
