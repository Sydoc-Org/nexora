USE [nexora]
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations] DROP CONSTRAINT [FK_KundenmagazinIssueOrgs_Org]
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations] DROP CONSTRAINT [FK_KundenmagazinIssueOrgs_Issue]
GO
DROP INDEX [IX_KundenmagazinIssueOrgs_Org] ON [dbo].[KundenmagazinIssueOrganizations]
GO
DROP TABLE [dbo].[KundenmagazinIssueOrganizations]
GO
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[KundenmagazinIssueOrganizations](
	[IssueID] [int] NOT NULL,
	[OrganizationCode] [nvarchar](5) NOT NULL,
 CONSTRAINT [PK_KundenmagazinIssueOrganizations] PRIMARY KEY CLUSTERED 
(
	[IssueID] ASC,
	[OrganizationCode] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
) ON [PRIMARY]
GO
SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_KundenmagazinIssueOrgs_Org] ON [dbo].[KundenmagazinIssueOrganizations]
(
	[OrganizationCode] ASC,
	[IssueID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON) ON [PRIMARY]
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations]  WITH CHECK ADD  CONSTRAINT [FK_KundenmagazinIssueOrgs_Issue] FOREIGN KEY([IssueID])
REFERENCES [dbo].[KundenmagazinIssues] ([ID])
ON DELETE CASCADE
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations] CHECK CONSTRAINT [FK_KundenmagazinIssueOrgs_Issue]
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations]  WITH CHECK ADD  CONSTRAINT [FK_KundenmagazinIssueOrgs_Org] FOREIGN KEY([OrganizationCode])
REFERENCES [dbo].[Organizations] ([organizationcode])
GO
ALTER TABLE [dbo].[KundenmagazinIssueOrganizations] CHECK CONSTRAINT [FK_KundenmagazinIssueOrgs_Org]
GO
