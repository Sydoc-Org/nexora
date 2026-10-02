USE [nexora]
GO
ALTER TABLE [dbo].[ControllingCosts] DROP CONSTRAINT [CK_ControllingCosts_Month]
GO
ALTER TABLE [dbo].[ControllingCosts] DROP CONSTRAINT [DF_ControllingCosts_ChangedAt]
GO
DROP INDEX [IX_ControllingCosts_Month] ON [dbo].[ControllingCosts]
GO
DROP TABLE [dbo].[ControllingCosts]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ControllingCosts](
	[CostId] [int] IDENTITY(1,1) NOT NULL,
	[Month] [date] NOT NULL,
	[StreamKey] [nvarchar](50) NOT NULL,
	[Label] [nvarchar](200) NOT NULL,
	[Amount] [decimal](12, 2) NOT NULL,
	[ChangedAt] [datetime2](0) NOT NULL,
	[ChangedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_ControllingCosts] PRIMARY KEY CLUSTERED 
(
	[CostId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_ControllingCosts_Month] ON [dbo].[ControllingCosts]
(
	[Month] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ControllingCosts] ADD  CONSTRAINT [DF_ControllingCosts_ChangedAt]  DEFAULT (sysutcdatetime()) FOR [ChangedAt]
GO
ALTER TABLE [dbo].[ControllingCosts]  WITH CHECK ADD  CONSTRAINT [CK_ControllingCosts_Month] CHECK  ((datepart(day,[Month])=(1)))
GO
ALTER TABLE [dbo].[ControllingCosts] CHECK CONSTRAINT [CK_ControllingCosts_Month]
GO
