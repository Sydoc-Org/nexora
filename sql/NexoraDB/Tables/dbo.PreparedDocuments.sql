USE [nexora]
GO
ALTER TABLE [dbo].[PreparedDocuments] DROP CONSTRAINT [DF_PreparedDocuments_UploadedAt]
GO
ALTER TABLE [dbo].[PreparedDocuments] DROP CONSTRAINT [DF_PreparedDocuments_Prepared]
GO
ALTER TABLE [dbo].[PreparedDocuments] DROP CONSTRAINT [DF_PreparedDocuments_Collected]
GO
DROP TABLE [dbo].[PreparedDocuments]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PreparedDocuments](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[PID] [nvarchar](100) NOT NULL,
	[Collected] [bit] NOT NULL,
	[CollectedBy] [nvarchar](255) NULL,
	[Prepared] [bit] NOT NULL,
	[PreparedBy] [nvarchar](255) NULL,
	[UploadedBy] [int] NULL,
	[UploadedAt] [datetime2](7) NOT NULL,
	[UpdatedAt] [datetime2](7) NULL,
 CONSTRAINT [PK_PreparedDocuments] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
 CONSTRAINT [UQ_PreparedDocuments_PID] UNIQUE NONCLUSTERED 
(
	[PID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[PreparedDocuments] ADD  CONSTRAINT [DF_PreparedDocuments_Collected]  DEFAULT ((0)) FOR [Collected]
GO
ALTER TABLE [dbo].[PreparedDocuments] ADD  CONSTRAINT [DF_PreparedDocuments_Prepared]  DEFAULT ((0)) FOR [Prepared]
GO
ALTER TABLE [dbo].[PreparedDocuments] ADD  CONSTRAINT [DF_PreparedDocuments_UploadedAt]  DEFAULT (sysutcdatetime()) FOR [UploadedAt]
GO
