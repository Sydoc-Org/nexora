USE [nexora]
GO
ALTER TABLE [dbo].[StatusSamples] DROP CONSTRAINT [DF_StatusSamples_Ok]
GO
DROP INDEX [IX_StatusSamples_SampledAt] ON [dbo].[StatusSamples]
GO
DROP TABLE [dbo].[StatusSamples]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[StatusSamples](
	[ComponentKey] [nvarchar](200) NOT NULL,
	[SampledAt] [datetime2](0) NOT NULL,
	[LatencyMs] [int] NOT NULL,
	[Ok] [bit] NOT NULL,
 CONSTRAINT [PK_StatusSamples] PRIMARY KEY CLUSTERED 
(
	[ComponentKey] ASC,
	[SampledAt] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_StatusSamples_SampledAt] ON [dbo].[StatusSamples]
(
	[SampledAt] ASC
)
INCLUDE ( 	[ComponentKey],
	[LatencyMs],
	[Ok]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[StatusSamples] ADD  CONSTRAINT [DF_StatusSamples_Ok]  DEFAULT ((1)) FOR [Ok]
GO
