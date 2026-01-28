SET ANSI_PADDING ON
GO
CREATE NONCLUSTERED INDEX [IX_EM_Invoice_NexoraDocFieldSearch] ON [dbo].[EM_Invoice]
(
	[WorkItem] ASC,
	[ImportDatetime] ASC
)
INCLUDE([DocType],[DocBarcode],[CrdNO],[CRDNAME1],[BankPK],[GrossAmount],[NetAmount],[VatAmount],[DocCurrency],[InvoiceNR],[Bestellnummer],[Eingang],[Branch],[DocDate]) WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, SORT_IN_TEMPDB = OFF, DROP_EXISTING = OFF, ONLINE = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, OPTIMIZE_FOR_SEQUENTIAL_KEY = OFF) ON [PRIMARY]
GO
