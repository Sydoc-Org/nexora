USE [nexora]
GO
ALTER TABLE [dbo].[ControllingMonthClose] DROP CONSTRAINT [CK_ControllingMonthClose_Payload]
GO
ALTER TABLE [dbo].[ControllingMonthClose] DROP CONSTRAINT [DF_ControllingMonthClose_ClosedAt]
GO
DROP TABLE [dbo].[ControllingMonthClose]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ControllingMonthClose](
	[Month] [char](7) NOT NULL,
	[Payload] [nvarchar](max) NOT NULL,
	[ClosedAt] [datetime2](0) NOT NULL,
	[ClosedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_ControllingMonthClose] PRIMARY KEY CLUSTERED 
(
	[Month] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[ControllingMonthClose] ADD  CONSTRAINT [DF_ControllingMonthClose_ClosedAt]  DEFAULT (sysutcdatetime()) FOR [ClosedAt]
GO
ALTER TABLE [dbo].[ControllingMonthClose]  WITH CHECK ADD  CONSTRAINT [CK_ControllingMonthClose_Payload] CHECK  ((isjson([Payload])=(1)))
GO
ALTER TABLE [dbo].[ControllingMonthClose] CHECK CONSTRAINT [CK_ControllingMonthClose_Payload]
GO
