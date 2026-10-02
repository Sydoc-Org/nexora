USE [nexora]
GO
ALTER TABLE [dbo].[ControllingStreamProjects] DROP CONSTRAINT [DF_ControllingStreamProjects_LinkedAt]
GO
DROP TABLE [dbo].[ControllingStreamProjects]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ControllingStreamProjects](
	[ProjectId] [int] NOT NULL,
	[StreamKey] [nvarchar](50) NULL,
	[Note] [nvarchar](200) NULL,
	[LinkedAt] [datetime2](0) NOT NULL,
	[LinkedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_ControllingStreamProjects] PRIMARY KEY CLUSTERED 
(
	[ProjectId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ControllingStreamProjects] ADD  CONSTRAINT [DF_ControllingStreamProjects_LinkedAt]  DEFAULT (sysutcdatetime()) FOR [LinkedAt]
GO
