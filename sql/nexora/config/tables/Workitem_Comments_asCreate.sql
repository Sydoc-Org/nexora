USE [nexora]
GO

/****** Objekt:  Table [dbo].[Workitem_Comments]    Skriptdatum: 27.04.2026 14:26:47 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[Workitem_Comments](
	[CommentID] [int] IDENTITY(1,1) NOT NULL,
	[WorkitemId] [nvarchar](255) NOT NULL,
	[UserID] [int] NULL,
	[CommentText] [nvarchar](max) NOT NULL,
	[Timestamp] [datetime] NULL,
PRIMARY KEY CLUSTERED 
(
	[CommentID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO

ALTER TABLE [dbo].[Workitem_Comments] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO

ALTER TABLE [dbo].[Workitem_Comments]  WITH CHECK ADD FOREIGN KEY([UserID])
REFERENCES [dbo].[Users] ([userID])
GO

