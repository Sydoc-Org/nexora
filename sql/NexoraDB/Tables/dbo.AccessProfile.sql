USE [nexora]
GO
ALTER TABLE [dbo].[AccessProfile] DROP CONSTRAINT [FK_AccessProfile_Organizations]
GO
ALTER TABLE [dbo].[AccessProfile] DROP CONSTRAINT [DF_AccessProfile_Rank]
GO
DROP TABLE [dbo].[AccessProfile]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[AccessProfile](
	[AccessID] [int] IDENTITY(1,1) NOT NULL,
	[Name] [nvarchar](50) NOT NULL,
	[Description] [nvarchar](200) NULL,
	[OrganizationCode] [nvarchar](5) NULL,
	[Rank] [int] NOT NULL,
PRIMARY KEY CLUSTERED 
(
	[AccessID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
 CONSTRAINT [UQ_AccessProfileName] UNIQUE NONCLUSTERED 
(
	[Name] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[AccessProfile] ADD  CONSTRAINT [DF_AccessProfile_Rank]  DEFAULT ((0)) FOR [Rank]
GO
ALTER TABLE [dbo].[AccessProfile]  WITH CHECK ADD  CONSTRAINT [FK_AccessProfile_Organizations] FOREIGN KEY([OrganizationCode])
REFERENCES [dbo].[Organizations] ([organizationcode])
GO
ALTER TABLE [dbo].[AccessProfile] CHECK CONSTRAINT [FK_AccessProfile_Organizations]
GO
