USE [Generali]
GO
ALTER TABLE [dbo].[DocumentSapMetadata] DROP CONSTRAINT [FK_DocumentSapMetadata_Documents]
GO
DROP TABLE [dbo].[DocumentSapMetadata]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[DocumentSapMetadata](
	[DocumentRecordId] [int] NOT NULL,
	[SapComponents] [varchar](20) NULL,
	[SapComponentSize] [varchar](20) NULL,
	[SapContentType] [varchar](50) NULL,
	[SapDocumentId] [varchar](64) NULL,
	[SapDocumentProtection] [varchar](20) NULL,
	[SapType] [varchar](20) NULL,
 CONSTRAINT [PK_DocumentSapMetadata] PRIMARY KEY CLUSTERED 
(
	[DocumentRecordId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[DocumentSapMetadata]  WITH CHECK ADD  CONSTRAINT [FK_DocumentSapMetadata_Documents] FOREIGN KEY([DocumentRecordId])
REFERENCES [dbo].[Documents] ([Id])
GO
ALTER TABLE [dbo].[DocumentSapMetadata] CHECK CONSTRAINT [FK_DocumentSapMetadata_Documents]
GO
