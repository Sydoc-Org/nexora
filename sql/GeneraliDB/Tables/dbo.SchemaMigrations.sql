USE [Generali]
GO
ALTER TABLE [dbo].[SchemaMigrations] DROP CONSTRAINT [DF_SchemaMigrations_AppliedBy]
GO
ALTER TABLE [dbo].[SchemaMigrations] DROP CONSTRAINT [DF_SchemaMigrations_AppliedAt]
GO
DROP TABLE [dbo].[SchemaMigrations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[SchemaMigrations](
	[FileName] [nvarchar](255) NOT NULL,
	[AppliedAt] [datetime2](7) NOT NULL,
	[AppliedBy] [nvarchar](128) NOT NULL,
	[Checksum] [binary](32) NOT NULL,
 CONSTRAINT [PK_SchemaMigrations] PRIMARY KEY CLUSTERED 
(
	[FileName] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[SchemaMigrations] ADD  CONSTRAINT [DF_SchemaMigrations_AppliedAt]  DEFAULT (sysutcdatetime()) FOR [AppliedAt]
GO
ALTER TABLE [dbo].[SchemaMigrations] ADD  CONSTRAINT [DF_SchemaMigrations_AppliedBy]  DEFAULT (suser_sname()) FOR [AppliedBy]
GO
