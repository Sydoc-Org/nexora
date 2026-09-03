USE [nexora]
GO
ALTER TABLE [dbo].[Organizations] DROP CONSTRAINT [FK_Organizations_Tenants]
GO
ALTER TABLE [dbo].[Organizations] DROP CONSTRAINT [FK_Organizations_Clients]
GO
DROP TABLE [dbo].[Organizations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Organizations](
	[organizationcode] [nvarchar](5) NOT NULL,
	[Organization] [nvarchar](200) NULL,
	[BrandName] [nvarchar](100) NULL,
	[BrandAccentHex] [nvarchar](7) NULL,
	[BrandLogoFile] [nvarchar](255) NULL,
	[TenantCode] [nvarchar](50) NULL,
	[ClientCode] [nvarchar](50) NULL,
PRIMARY KEY CLUSTERED 
(
	[organizationcode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Organizations]  WITH CHECK ADD  CONSTRAINT [FK_Organizations_Clients] FOREIGN KEY([ClientCode])
REFERENCES [dbo].[Clients] ([ClientCode])
GO
ALTER TABLE [dbo].[Organizations] CHECK CONSTRAINT [FK_Organizations_Clients]
GO
ALTER TABLE [dbo].[Organizations]  WITH CHECK ADD  CONSTRAINT [FK_Organizations_Tenants] FOREIGN KEY([TenantCode])
REFERENCES [dbo].[Tenants] ([TenantCode])
GO
ALTER TABLE [dbo].[Organizations] CHECK CONSTRAINT [FK_Organizations_Tenants]
GO
