CREATE NONCLUSTERED INDEX [IX_PriveraInvoice_NexoraDocFieldSearch] ON [dbo].[PriveraInvoice]
(
	[WID] ASC,
	[ImportTime] ASC
)
INCLUDE([DocType],[Barcode],[CRD_NR],[CRD_NAME_1],[BankPK],[GrossAmount],[NetAmount],[VatAmount],[DocCurrency],[InvoiceNR],[ISTEC],[ESR],[BestellNummer],[Mandant],[DocSource],[EigentuemerNr],[LiegenschaftsNr]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
