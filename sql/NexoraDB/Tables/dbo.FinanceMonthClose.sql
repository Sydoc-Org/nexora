USE [nexora]
GO
ALTER TABLE [dbo].[FinanceMonthClose] DROP CONSTRAINT [DF_FinanceMonthClose_ClosedAt]
GO
DROP TABLE [dbo].[FinanceMonthClose]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
SET ANSI_PADDING ON
GO
CREATE TABLE [dbo].[FinanceMonthClose](
	[Month] [char](7) NOT NULL,
	[SectionKey] [varchar](64) NOT NULL,
	[Payload] [nvarchar](max) NOT NULL,
	[ClosedAt] [datetime2](0) NOT NULL,
	[ClosedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_FinanceMonthClose] PRIMARY KEY CLUSTERED 
(
	[Month] ASC,
	[SectionKey] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[FinanceMonthClose] ADD  CONSTRAINT [DF_FinanceMonthClose_ClosedAt]  DEFAULT (sysutcdatetime()) FOR [ClosedAt]
GO
