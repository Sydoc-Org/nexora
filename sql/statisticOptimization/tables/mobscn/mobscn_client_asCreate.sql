SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TABLE [dbo].[MOBSCN_CLIENT](
	[ID] [int] IDENTITY(1,1) NOT NULL,
	[WorkItemID] [int] NOT NULL,
	[PID] [nvarchar](50) NULL,
	[ScanBatchNr] [nvarchar](50) NULL,
	[ScanArchivBoxNr] [nvarchar](50) NULL,
	[ScanDatum] [datetime] NULL,
	[DatumImportiert] [datetime] NULL,
	[DatumInSplitting] [datetime] NULL,
	[DatumInKlassifikation] [datetime] NULL,
	[DatumInSupervisor] [datetime] NULL,
	[DatumInExport] [datetime] NULL,
	[DatumLieferung] [datetime] NULL,
	[PersonenAkteID] [nvarchar](50) NULL,
	[AnstellungsAkteID] [nvarchar](50) NULL,
	[DokArtIDZielsystem] [nvarchar](250) NULL,
	[DokArtIDSydoc] [nvarchar](250) NULL,
	[DokArtName] [nvarchar](250) NULL,
	[DokDatum] [nvarchar](250) NULL,
	[RegisterIDZielsystem] [nvarchar](250) NULL,
	[StammdatenDeckblattTyp] [nvarchar](50) NULL,
	[StammdatenGeburtsdatum] [nvarchar](50) NULL,
	[StammdatenVorname] [nvarchar](250) NULL,
	[StammdatenNachname] [nvarchar](250) NULL,
	[StammdatenTrennblattID] [nvarchar](250) NULL,
	[ZielsystemDateiname] [nvarchar](250) NULL,
	[UpdatedAt] [datetime] NULL,
PRIMARY KEY CLUSTERED 
(
	[WorkItemID] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
) ON [PRIMARY]
GO
CREATE NONCLUSTERED INDEX [IX_MOBSCN_CLIENT_NexoraDocFieldSearch] ON [dbo].[MOBSCN_CLIENT]
(
	[WorkItemID] ASC,
	[DatumImportiert] ASC,
	[DatumLieferung] ASC
)
INCLUDE([ScanBatchNr],[PID],[ScanArchivBoxNr],[PersonenAkteID],[AnstellungsAkteID],[DokArtIDZielsystem],[DokArtIDSydoc],[DokArtName],[DokDatum],[RegisterIDZielsystem],[StammdatenDeckblattTyp],[StammdatenGeburtsdatum],[StammdatenVorname],[StammdatenNachname],[StammdatenTrennblattID],[ZielsystemDateiname]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
