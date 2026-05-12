USE [nexora]
GO
ALTER TABLE [dbo].[Logs] DROP CONSTRAINT [DF__Logs2__Timestamp__4959E263]
GO
DROP TABLE [dbo].[Logs]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[Logs](
	[LogID] [int] IDENTITY(1,1) NOT NULL,
	[Timestamp] [datetime2](7) NOT NULL,
	[SessionID] [nvarchar](255) NULL,
	[RequestIpAddress] [nvarchar](45) NULL,
	[UserID] [int] NULL,
	[Username] [nvarchar](100) NULL,
	[HttpRequestMethod] [nvarchar](20) NULL,
	[Path] [nvarchar](100) NULL,
	[HttpResponseCode] [nvarchar](100) NULL,
	[Args] [nvarchar](max) NULL,
	[durationSeconds] [float] NULL,
PRIMARY KEY CLUSTERED 
(
	[LogID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
ALTER TABLE [dbo].[Logs] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO
