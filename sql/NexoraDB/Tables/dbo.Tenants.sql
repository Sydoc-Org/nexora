USE [nexora]
GO
ALTER TABLE [dbo].[Tenants] DROP CONSTRAINT [FK_Tenants_Organizations]
GO
ALTER TABLE [dbo].[Tenants] DROP CONSTRAINT [FK_Tenants_Clients]
GO
ALTER TABLE [dbo].[Tenants] DROP CONSTRAINT [DF_Tenants_IsActive]
GO
DROP TABLE [dbo].[Tenants]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Tenants](
	[TenantCode] [nvarchar](50) NOT NULL,
	[DisplayName] [nvarchar](100) NOT NULL,
	[OrganizationCode] [nvarchar](5) NOT NULL,
	[ClientCode] [nvarchar](50) NOT NULL,
	[IsActive] [bit] NOT NULL,
 CONSTRAINT [PK_Tenants] PRIMARY KEY CLUSTERED 
(
	[TenantCode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Tenants] ADD  CONSTRAINT [DF_Tenants_IsActive]  DEFAULT ((1)) FOR [IsActive]
GO
ALTER TABLE [dbo].[Tenants]  WITH CHECK ADD  CONSTRAINT [FK_Tenants_Clients] FOREIGN KEY([ClientCode])
REFERENCES [dbo].[Clients] ([ClientCode])
GO
ALTER TABLE [dbo].[Tenants] CHECK CONSTRAINT [FK_Tenants_Clients]
GO
ALTER TABLE [dbo].[Tenants]  WITH CHECK ADD  CONSTRAINT [FK_Tenants_Organizations] FOREIGN KEY([OrganizationCode])
REFERENCES [dbo].[Organizations] ([organizationcode])
GO
ALTER TABLE [dbo].[Tenants] CHECK CONSTRAINT [FK_Tenants_Organizations]
GO
