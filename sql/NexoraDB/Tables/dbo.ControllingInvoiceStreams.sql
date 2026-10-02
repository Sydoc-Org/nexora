USE [nexora]
GO
ALTER TABLE [dbo].[ControllingInvoiceStreams] DROP CONSTRAINT [DF_ControllingInvoiceStreams_LinkedAt]
GO
DROP TABLE [dbo].[ControllingInvoiceStreams]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ControllingInvoiceStreams](
	[InvoiceId] [int] NOT NULL,
	[InvoiceNr] [nvarchar](50) NOT NULL,
	[StreamKey] [nvarchar](50) NULL,
	[Note] [nvarchar](200) NULL,
	[LinkedAt] [datetime2](0) NOT NULL,
	[LinkedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_ControllingInvoiceStreams] PRIMARY KEY CLUSTERED 
(
	[InvoiceId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[ControllingInvoiceStreams] ADD  CONSTRAINT [DF_ControllingInvoiceStreams_LinkedAt]  DEFAULT (sysutcdatetime()) FOR [LinkedAt]
GO
