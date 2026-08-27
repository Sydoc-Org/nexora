USE [nexora]
GO
ALTER TABLE [dbo].[Clients] DROP CONSTRAINT [DF_Clients_IsActive]
GO
DROP TABLE [dbo].[Clients]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Clients](
	[ClientCode] [nvarchar](50) NOT NULL,
	[DisplayName] [nvarchar](100) NOT NULL,
	[Dialect] [nvarchar](20) NOT NULL,
	[RuntimeEngineKey] [nvarchar](50) NOT NULL,
	[StatsEngineKey] [nvarchar](50) NULL,
	[StatsDialect] [nvarchar](20) NULL,
	[DocfieldsEngineKey] [nvarchar](50) NULL,
	[DocfieldsDialect] [nvarchar](20) NULL,
	[OctoDomain] [nvarchar](255) NULL,
	[SecretRef] [nvarchar](50) NULL,
	[IsActive] [bit] NOT NULL,
 CONSTRAINT [PK_Clients] PRIMARY KEY CLUSTERED 
(
	[ClientCode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Clients] ADD  CONSTRAINT [DF_Clients_IsActive]  DEFAULT ((1)) FOR [IsActive]
GO
