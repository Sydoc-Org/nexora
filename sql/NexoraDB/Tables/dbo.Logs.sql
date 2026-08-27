USE [nexora]
GO
ALTER TABLE [dbo].[Logs] DROP CONSTRAINT [DF__Logs2__Timestamp__4959E263]
GO
DROP INDEX [IX_Logs_Timestamp] ON [dbo].[Logs]
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
CREATE NONCLUSTERED INDEX [IX_Logs_Timestamp] ON [dbo].[Logs]
(
	[Timestamp] DESC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[Logs] ADD  DEFAULT (getdate()) FOR [Timestamp]
GO
