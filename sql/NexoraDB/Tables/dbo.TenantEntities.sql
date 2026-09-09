USE [nexora]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [CK_TenantEntities_Status]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [CK_TenantEntities_Kind]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [CK_TenantEntities_EngineRole]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [FK_TenantEntities_Tenants]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [FK_TenantEntities_Clients]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [DF_TenantEntities_Status]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [DF_TenantEntities_SortOrder]
GO
ALTER TABLE [dbo].[TenantEntities] DROP CONSTRAINT [DF_TenantEntities_EngineRole]
GO
DROP TABLE [dbo].[TenantEntities]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TenantEntities](
	[TenantCode] [nvarchar](50) NOT NULL,
	[EntityKey] [nvarchar](100) NOT NULL,
	[SourceObject] [nvarchar](256) NOT NULL,
	[Kind] [nvarchar](16) NOT NULL,
	[EngineRole] [nvarchar](16) NOT NULL,
	[IdColumn] [nvarchar](128) NOT NULL,
	[LabelEn] [nvarchar](120) NOT NULL,
	[LabelDe] [nvarchar](120) NULL,
	[LabelFr] [nvarchar](120) NULL,
	[LabelIt] [nvarchar](120) NULL,
	[SortOrder] [int] NOT NULL,
	[Status] [nvarchar](8) NOT NULL,
	[ClientCode] [nvarchar](50) NOT NULL,
 CONSTRAINT [PK_TenantEntities] PRIMARY KEY CLUSTERED 
(
	[TenantCode] ASC,
	[EntityKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[TenantEntities] ADD  CONSTRAINT [DF_TenantEntities_EngineRole]  DEFAULT ('runtime') FOR [EngineRole]
GO
ALTER TABLE [dbo].[TenantEntities] ADD  CONSTRAINT [DF_TenantEntities_SortOrder]  DEFAULT ((100)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[TenantEntities] ADD  CONSTRAINT [DF_TenantEntities_Status]  DEFAULT ('draft') FOR [Status]
GO
ALTER TABLE [dbo].[TenantEntities]  WITH CHECK ADD  CONSTRAINT [FK_TenantEntities_Clients] FOREIGN KEY([ClientCode])
REFERENCES [dbo].[Clients] ([ClientCode])
GO
ALTER TABLE [dbo].[TenantEntities] CHECK CONSTRAINT [FK_TenantEntities_Clients]
GO
ALTER TABLE [dbo].[TenantEntities]  WITH CHECK ADD  CONSTRAINT [FK_TenantEntities_Tenants] FOREIGN KEY([TenantCode])
REFERENCES [dbo].[Tenants] ([TenantCode])
GO
ALTER TABLE [dbo].[TenantEntities] CHECK CONSTRAINT [FK_TenantEntities_Tenants]
GO
ALTER TABLE [dbo].[TenantEntities]  WITH CHECK ADD  CONSTRAINT [CK_TenantEntities_EngineRole] CHECK  (([EngineRole]='docfields' OR [EngineRole]='stats' OR [EngineRole]='runtime'))
GO
ALTER TABLE [dbo].[TenantEntities] CHECK CONSTRAINT [CK_TenantEntities_EngineRole]
GO
ALTER TABLE [dbo].[TenantEntities]  WITH CHECK ADD  CONSTRAINT [CK_TenantEntities_Kind] CHECK  (([Kind]='lookup' OR [Kind]='entries' OR [Kind]='documents'))
GO
ALTER TABLE [dbo].[TenantEntities] CHECK CONSTRAINT [CK_TenantEntities_Kind]
GO
ALTER TABLE [dbo].[TenantEntities]  WITH CHECK ADD  CONSTRAINT [CK_TenantEntities_Status] CHECK  (([Status]='active' OR [Status]='draft'))
GO
ALTER TABLE [dbo].[TenantEntities] CHECK CONSTRAINT [CK_TenantEntities_Status]
GO
