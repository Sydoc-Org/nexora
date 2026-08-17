USE [nexora]
GO
ALTER TABLE [dbo].[LoginLockout] DROP CONSTRAINT [DF_LoginLockout_updated_at]
GO
ALTER TABLE [dbo].[LoginLockout] DROP CONSTRAINT [DF__LoginLock__faile__20E1DCB5]
GO
DROP TABLE [dbo].[LoginLockout]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[LoginLockout](
	[userid] [nvarchar](64) NOT NULL,
	[failed_count] [int] NOT NULL,
	[locked_until] [datetime] NULL,
	[updated_at] [datetime] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[userid] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[LoginLockout] ADD  DEFAULT ((0)) FOR [failed_count]
GO
ALTER TABLE [dbo].[LoginLockout] ADD  CONSTRAINT [DF_LoginLockout_updated_at]  DEFAULT (getutcdate()) FOR [updated_at]
GO
