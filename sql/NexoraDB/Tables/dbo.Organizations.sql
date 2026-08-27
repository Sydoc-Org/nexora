USE [nexora]
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
PRIMARY KEY CLUSTERED 
(
	[organizationcode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
