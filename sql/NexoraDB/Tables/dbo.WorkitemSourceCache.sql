USE [nexora]
GO
ALTER TABLE [dbo].[WorkitemSourceCache] DROP CONSTRAINT [DF_WorkitemSourceCache_ResolvedAt]
GO
DROP TABLE [dbo].[WorkitemSourceCache]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[WorkitemSourceCache](
	[WorkItemID] [nvarchar](255) NOT NULL,
	[ClientCode] [nvarchar](50) NOT NULL,
	[ResolvedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_WorkitemSourceCache] PRIMARY KEY CLUSTERED 
(
	[WorkItemID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[WorkitemSourceCache] ADD  CONSTRAINT [DF_WorkitemSourceCache_ResolvedAt]  DEFAULT (sysutcdatetime()) FOR [ResolvedAt]
GO
