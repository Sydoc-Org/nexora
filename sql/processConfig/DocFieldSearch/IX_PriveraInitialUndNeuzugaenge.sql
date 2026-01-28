SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_PriveraInitialUndNeuzugaenge_NexoraDocFieldSearch] ON [dbo].[PriveraInitialUndNeuzugaenge]
(
	[WorkitemID] ASC,
	[Export] ASC
)
INCLUDE([Barcode],[Eigentuemernummer],[ID_Miet],[Liegenschaftsnummer],[Trennblatt],[ID],[ArchivBoxNummer]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
