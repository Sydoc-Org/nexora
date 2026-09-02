USE [nexora]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [CK_TenantFields_Status]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [CK_TenantFields_SemanticRole]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [FK_TenantFields_TenantEntities]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [DF_TenantFields_Status]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [DF_TenantFields_SortOrder]
GO
ALTER TABLE [dbo].[TenantFields] DROP CONSTRAINT [DF_TenantFields_IsVisible]
GO
DROP TABLE [dbo].[TenantFields]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TenantFields](
	[TenantCode] [nvarchar](50) NOT NULL,
	[EntityKey] [nvarchar](100) NOT NULL,
	[ColumnName] [nvarchar](128) NOT NULL,
	[SemanticRole] [nvarchar](16) NOT NULL,
	[LookupEntity] [nvarchar](100) NULL,
	[LabelEn] [nvarchar](120) NOT NULL,
	[LabelDe] [nvarchar](120) NULL,
	[LabelFr] [nvarchar](120) NULL,
	[LabelIt] [nvarchar](120) NULL,
	[IsVisible] [bit] NOT NULL,
	[SortOrder] [int] NOT NULL,
	[Status] [nvarchar](8) NOT NULL,
 CONSTRAINT [PK_TenantFields] PRIMARY KEY CLUSTERED 
(
	[TenantCode] ASC,
	[EntityKey] ASC,
	[ColumnName] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[TenantFields] ADD  CONSTRAINT [DF_TenantFields_IsVisible]  DEFAULT ((1)) FOR [IsVisible]
GO
ALTER TABLE [dbo].[TenantFields] ADD  CONSTRAINT [DF_TenantFields_SortOrder]  DEFAULT ((100)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[TenantFields] ADD  CONSTRAINT [DF_TenantFields_Status]  DEFAULT ('draft') FOR [Status]
GO
ALTER TABLE [dbo].[TenantFields]  WITH CHECK ADD  CONSTRAINT [FK_TenantFields_TenantEntities] FOREIGN KEY([TenantCode], [EntityKey])
REFERENCES [dbo].[TenantEntities] ([TenantCode], [EntityKey])
GO
ALTER TABLE [dbo].[TenantFields] CHECK CONSTRAINT [FK_TenantFields_TenantEntities]
GO
ALTER TABLE [dbo].[TenantFields]  WITH CHECK ADD  CONSTRAINT [CK_TenantFields_SemanticRole] CHECK  (([SemanticRole]='flag' OR [SemanticRole]='text' OR [SemanticRole]='count' OR [SemanticRole]='identifier' OR [SemanticRole]='person' OR [SemanticRole]='category' OR [SemanticRole]='money' OR [SemanticRole]='date'))
GO
ALTER TABLE [dbo].[TenantFields] CHECK CONSTRAINT [CK_TenantFields_SemanticRole]
GO
ALTER TABLE [dbo].[TenantFields]  WITH CHECK ADD  CONSTRAINT [CK_TenantFields_Status] CHECK  (([Status]='active' OR [Status]='draft'))
GO
ALTER TABLE [dbo].[TenantFields] CHECK CONSTRAINT [CK_TenantFields_Status]
GO
