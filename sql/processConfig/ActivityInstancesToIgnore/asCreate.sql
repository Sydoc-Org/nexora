SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ActivityInstancesToIgnore](
	[ProcessName] [nvarchar](100) NOT NULL,
	[ActivityInstanceName] [nvarchar](100) NOT NULL
) ON [PRIMARY]
GO
