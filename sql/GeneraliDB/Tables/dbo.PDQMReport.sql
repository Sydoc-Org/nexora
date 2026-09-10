USE [Generali]
GO
DROP TABLE [dbo].[PDQMReport]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[PDQMReport](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[Quantity] [int] NULL,
	[ForDate] [date] NULL,
	[UserID] [int] NULL,
	[RecordDateTime] [datetime] NULL,
	[ParentCategory] [nvarchar](100) NULL,
	[ParentSubCategory] [nvarchar](100) NULL,
	[SubCategory] [nvarchar](100) NULL,
 CONSTRAINT [PK_PDQMReport] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
