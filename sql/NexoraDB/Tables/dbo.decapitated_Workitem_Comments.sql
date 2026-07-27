USE [nexora]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Comments] DROP CONSTRAINT [DF__Workitem___Times__3C34F16F]
GO
DROP TABLE [dbo].[decapitated_Workitem_Comments]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[decapitated_Workitem_Comments](
	[CommentID] [int] IDENTITY(1,1) NOT NULL,
	[WorkitemId] [nvarchar](255) NOT NULL,
	[UserID] [int] NULL,
	[CommentText] [nvarchar](max) NOT NULL,
	[Timestamp] [datetime] NULL,
PRIMARY KEY CLUSTERED 
(
	[CommentID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Comments] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO
