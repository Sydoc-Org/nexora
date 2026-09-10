USE [Generali]
GO
DROP TABLE [dbo].[ProjectManagement]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[ProjectManagement](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[EffortInHours] [float] NULL,
	[UserID] [int] NULL,
	[ForDate] [date] NULL,
	[Category] [nvarchar](50) NULL,
	[Comment] [nvarchar](max) NULL,
	[RecordDateTime] [datetime] NULL,
 CONSTRAINT [PK_ProjectManagement] PRIMARY KEY CLUSTERED 
(
	[ID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
