USE [nexora]
GO
ALTER TABLE [dbo].[FinanceRates] DROP CONSTRAINT [CK_FinanceRates_Value]
GO
ALTER TABLE [dbo].[FinanceRates] DROP CONSTRAINT [CK_FinanceRates_Range]
GO
ALTER TABLE [dbo].[FinanceRates] DROP CONSTRAINT [CK_FinanceRates_Kind]
GO
ALTER TABLE [dbo].[FinanceRates] DROP CONSTRAINT [DF_FinanceRates_ChangedAt]
GO
DROP TABLE [dbo].[FinanceRates]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[FinanceRates](
	[RateId] [int] IDENTITY(1,1) NOT NULL,
	[Kind] [nvarchar](20) NOT NULL,
	[StreamKey] [nvarchar](50) NULL,
	[Value] [decimal](10, 2) NOT NULL,
	[ValidFrom] [date] NOT NULL,
	[ValidTo] [date] NULL,
	[ChangedAt] [datetime2](0) NOT NULL,
	[ChangedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_FinanceRates] PRIMARY KEY CLUSTERED 
(
	[RateId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[FinanceRates] ADD  CONSTRAINT [DF_FinanceRates_ChangedAt]  DEFAULT (sysutcdatetime()) FOR [ChangedAt]
GO
ALTER TABLE [dbo].[FinanceRates]  WITH CHECK ADD  CONSTRAINT [CK_FinanceRates_Kind] CHECK  (([Kind]=N'fte_day_hours' OR [Kind]=N'hourly'))
GO
ALTER TABLE [dbo].[FinanceRates] CHECK CONSTRAINT [CK_FinanceRates_Kind]
GO
ALTER TABLE [dbo].[FinanceRates]  WITH CHECK ADD  CONSTRAINT [CK_FinanceRates_Range] CHECK  (([ValidTo] IS NULL OR [ValidTo]>=[ValidFrom]))
GO
ALTER TABLE [dbo].[FinanceRates] CHECK CONSTRAINT [CK_FinanceRates_Range]
GO
ALTER TABLE [dbo].[FinanceRates]  WITH CHECK ADD  CONSTRAINT [CK_FinanceRates_Value] CHECK  (([Value]>(0)))
GO
ALTER TABLE [dbo].[FinanceRates] CHECK CONSTRAINT [CK_FinanceRates_Value]
GO
