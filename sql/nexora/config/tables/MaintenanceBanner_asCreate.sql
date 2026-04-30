USE [nexora]
GO

SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[MaintenanceBanner](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[Title] [nvarchar](200) NULL,
	[Message] [nvarchar](2000) NOT NULL,
	[StartAt] [datetime2](7) NOT NULL,
	[EndAt] [datetime2](7) NOT NULL,
	[Severity] [varchar](20) NOT NULL,
	[Active] [bit] NOT NULL,
	[BlockAccess] [bit] NOT NULL,
	[CreatedBy] [int] NULL,
	[CreatedAt] [datetime2](7) NOT NULL,
PRIMARY KEY CLUSTERED
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ('info') FOR [Severity]
GO

ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ((1)) FOR [Active]
GO

ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT ((0)) FOR [BlockAccess]
GO

ALTER TABLE [dbo].[MaintenanceBanner] ADD  DEFAULT (getdate()) FOR [CreatedAt]
GO

CREATE INDEX [IX_MaintenanceBanner_Window] ON [dbo].[MaintenanceBanner]([Active], [StartAt], [EndAt])
GO

-- If the table already exists from the prior version, run this instead of recreating:
-- ALTER TABLE [dbo].[MaintenanceBanner] ADD [BlockAccess] [bit] NOT NULL CONSTRAINT DF_MaintenanceBanner_BlockAccess DEFAULT ((0))
-- GO
