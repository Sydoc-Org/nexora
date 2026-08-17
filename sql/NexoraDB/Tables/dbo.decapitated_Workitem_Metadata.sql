USE [nexora]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Metadata] DROP CONSTRAINT [DF__Workitem___LastU__3D2915A8]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Metadata] DROP CONSTRAINT [DF__Workitem___Prior__440B1D61]
GO
DROP TABLE [dbo].[decapitated_Workitem_Metadata]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[decapitated_Workitem_Metadata](
	[MetadataID] [int] IDENTITY(1,1) NOT NULL,
	[WorkitemId] [nvarchar](255) NOT NULL,
	[Priority] [int] NULL,
	[LastUpdatedByUserID] [int] NULL,
	[LastUpdatedAt] [datetime] NULL,
	[AssignedUserID] [int] NULL,
PRIMARY KEY CLUSTERED 
(
	[MetadataID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY],
UNIQUE NONCLUSTERED 
(
	[WorkitemId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Metadata] ADD  DEFAULT ((0)) FOR [Priority]
GO
ALTER TABLE [dbo].[decapitated_Workitem_Metadata] ADD  DEFAULT (getdate()) FOR [LastUpdatedAt]
GO
