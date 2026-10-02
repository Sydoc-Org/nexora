USE [nexora]
GO
ALTER TABLE [dbo].[FinanceBexioContacts] DROP CONSTRAINT [DF_FinanceBexioContacts_LinkedAt]
GO
DROP INDEX [IX_FinanceBexioContacts_Client] ON [dbo].[FinanceBexioContacts]
GO
DROP TABLE [dbo].[FinanceBexioContacts]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[FinanceBexioContacts](
	[ContactId] [int] NOT NULL,
	[Client] [nvarchar](100) NOT NULL,
	[LinkedAt] [datetime2](0) NOT NULL,
	[LinkedBy] [nvarchar](100) NOT NULL,
 CONSTRAINT [PK_FinanceBexioContacts] PRIMARY KEY CLUSTERED 
(
	[ContactId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_FinanceBexioContacts_Client] ON [dbo].[FinanceBexioContacts]
(
	[Client] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[FinanceBexioContacts] ADD  CONSTRAINT [DF_FinanceBexioContacts_LinkedAt]  DEFAULT (sysutcdatetime()) FOR [LinkedAt]
GO
