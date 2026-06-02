USE [nexora]
GO
ALTER TABLE [dbo].[ReportingSqlAck] DROP CONSTRAINT [DF_ReportingSqlAck_AcceptedAt]
GO
DROP TABLE [dbo].[ReportingSqlAck]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ReportingSqlAck](
	[UserID] [int] NOT NULL,
	[AcceptedAt] [datetime2](7) NOT NULL,
 CONSTRAINT [PK_ReportingSqlAck] PRIMARY KEY CLUSTERED 
(
	[UserID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ReportingSqlAck] ADD  CONSTRAINT [DF_ReportingSqlAck_AcceptedAt]  DEFAULT (sysutcdatetime()) FOR [AcceptedAt]
GO
