SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_PriveraPosteingang_NexoraDocFieldSearch] ON [dbo].[PriveraPosteingang]
(
	[WorkItemID] ASC,
	[ImportDatetime] ASC
)
INCLUDE([Dokumenttyp],[Barcode],[EigentuemerNr],[MietverhaeltnisNr],[Einschreiben],[Niederlassung],[DokDatum],[Nachsendung],[Abteilung],[Sendungsbarcode],[Empfaenger],[Vertraulichkeit],[LiegenschaftsNr]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
