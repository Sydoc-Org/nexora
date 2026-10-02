USE [nexora]
GO
ALTER TABLE [dbo].[ControllingVendorStreams] DROP CONSTRAINT [DF_ControllingVendorStreams_LinkedAt]
GO
DROP TABLE [dbo].[ControllingVendorStreams]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ControllingVendorStreams](
	[Match] [nvarchar](100) NOT NULL,
	[StreamKey] [nvarchar](50) NOT NULL,
	[Label] [nvarchar](200) NOT NULL,
	[LinkedAt] [datetime2](0) NOT NULL,
	[LinkedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_ControllingVendorStreams] PRIMARY KEY CLUSTERED 
(
	[Match] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ControllingVendorStreams] ADD  CONSTRAINT [DF_ControllingVendorStreams_LinkedAt]  DEFAULT (sysutcdatetime()) FOR [LinkedAt]
GO
