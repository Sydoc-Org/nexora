USE [nexora]
GO
ALTER TABLE [dbo].[TenantPages] DROP CONSTRAINT [CK_TenantPages_Status]
GO
ALTER TABLE [dbo].[TenantPages] DROP CONSTRAINT [CK_TenantPages_PageType]
GO
ALTER TABLE [dbo].[TenantPages] DROP CONSTRAINT [FK_TenantPages_Tenants]
GO
ALTER TABLE [dbo].[TenantPages] DROP CONSTRAINT [DF_TenantPages_Status]
GO
ALTER TABLE [dbo].[TenantPages] DROP CONSTRAINT [DF_TenantPages_SortOrder]
GO
DROP TABLE [dbo].[TenantPages]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[TenantPages](
	[TenantCode] [nvarchar](50) NOT NULL,
	[PageKey] [nvarchar](100) NOT NULL,
	[PageType] [nvarchar](16) NOT NULL,
	[EntityKey] [nvarchar](100) NULL,
	[LayoutJSON] [nvarchar](max) NULL,
	[SortOrder] [int] NOT NULL,
	[Status] [nvarchar](8) NOT NULL,
 CONSTRAINT [PK_TenantPages] PRIMARY KEY CLUSTERED 
(
	[TenantCode] ASC,
	[PageKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[TenantPages] ADD  CONSTRAINT [DF_TenantPages_SortOrder]  DEFAULT ((100)) FOR [SortOrder]
GO
ALTER TABLE [dbo].[TenantPages] ADD  CONSTRAINT [DF_TenantPages_Status]  DEFAULT ('draft') FOR [Status]
GO
ALTER TABLE [dbo].[TenantPages]  WITH CHECK ADD  CONSTRAINT [FK_TenantPages_Tenants] FOREIGN KEY([TenantCode])
REFERENCES [dbo].[Tenants] ([TenantCode])
GO
ALTER TABLE [dbo].[TenantPages] CHECK CONSTRAINT [FK_TenantPages_Tenants]
GO
ALTER TABLE [dbo].[TenantPages]  WITH CHECK ADD  CONSTRAINT [CK_TenantPages_PageType] CHECK  (([PageType]='custom' OR [PageType]='crud' OR [PageType]='list'))
GO
ALTER TABLE [dbo].[TenantPages] CHECK CONSTRAINT [CK_TenantPages_PageType]
GO
ALTER TABLE [dbo].[TenantPages]  WITH CHECK ADD  CONSTRAINT [CK_TenantPages_Status] CHECK  (([Status]='active' OR [Status]='draft'))
GO
ALTER TABLE [dbo].[TenantPages] CHECK CONSTRAINT [CK_TenantPages_Status]
GO
