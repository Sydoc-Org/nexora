USE [nexora]
GO

/****** Objekt:  Table [dbo].[SearchConfig]    Skriptdatum: 27.04.2026 15:24:28 ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[SearchConfig](
	[ProcessName] [varchar](100) NOT NULL,
	[TableName] [varchar](100) NULL,
	[TableAlias] [varchar](10) NULL,
	[JoinCondition] [varchar](255) NULL,
	[TimeFilter] [varchar](255) NULL,
	[col_doctype] [varchar](100) NULL,
	[col_docbarcode] [varchar](100) NULL,
	[col_crdno] [varchar](100) NULL,
	[col_crdname] [varchar](100) NULL,
	[SuggestionTimeFilter] [varchar](255) NULL,
	[col_bankpk] [varchar](100) NULL,
	[col_grossamount] [varchar](100) NULL,
	[col_netamount] [varchar](100) NULL,
	[col_vatamount] [varchar](100) NULL,
	[col_doccurrency] [varchar](100) NULL,
	[col_invoicenr] [varchar](100) NULL,
	[col_istec] [varchar](100) NULL,
	[col_esrreference] [varchar](100) NULL,
	[col_ordernumber] [varchar](100) NULL,
	[col_client] [varchar](100) NULL,
	[col_docsource] [varchar](100) NULL,
	[col_ownernr] [varchar](100) NULL,
	[col_tenancynr] [varchar](100) NULL,
	[col_registered] [varchar](100) NULL,
	[col_branch] [varchar](100) NULL,
	[col_docdate] [varchar](100) NULL,
	[col_forwarding] [varchar](100) NULL,
	[col_department] [varchar](100) NULL,
	[col_postcode] [varchar](100) NULL,
	[col_recipient] [varchar](100) NULL,
	[col_confidentiality] [varchar](100) NULL,
	[col_propertynr] [varchar](100) NULL,
	[col_separatorsheet] [varchar](100) NULL,
	[col_docid] [varchar](100) NULL,
	[col_archiveboxno] [varchar](100) NULL,
	[col_scanbatchnr] [nvarchar](100) NULL,
	[col_pid] [nvarchar](100) NULL,
	[col_personalfileid] [nvarchar](100) NULL,
	[col_employmentfileid] [nvarchar](100) NULL,
	[col_doctypeidtargetsystem] [nvarchar](100) NULL,
	[col_doctypeidsydoc] [nvarchar](100) NULL,
	[col_registeridtargetsystem] [nvarchar](100) NULL,
	[col_masterdataseparatorsheettype] [nvarchar](100) NULL,
	[col_masterdatabirthday] [nvarchar](100) NULL,
	[col_masterdatafirstname] [nvarchar](100) NULL,
	[col_masterdatalastname] [nvarchar](100) NULL,
	[col_masterdataseparatorsheetid] [nvarchar](100) NULL,
	[col_targetsystemfilename] [nvarchar](100) NULL,
	[col_emailfromaddress] [nvarchar](100) NULL,
PRIMARY KEY CLUSTERED 
(
	[ProcessName] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO

