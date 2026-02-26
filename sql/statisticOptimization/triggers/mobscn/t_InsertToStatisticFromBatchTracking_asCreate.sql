SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[t_InsertToStatisticFromBatchTracking] on [dbo].[BatchTracking]
after INSERT
as BEGIN
    set NOCOUNT on;

    INSERT Into SYDOC_Statistik.dbo.BankWIR
        (
        WorkItemID,
        PID,
        ScanBatchNr,
        ScanArchivBoxNr,
        ScanDatum,
        DatumImportiert,
        DatumInSplitting,
        DatumInKlassifikation,
        DatumInSupervisor,
        DatumInExport,
        UpdatedAt
        )
    SELECT
        WorkItemID,
        PID,
        ScanBatchNr,
        ScanArchivBoxNr,
        ScanDatum,
        DatumImportiert,
        DatumInSplitting,
        DatumInKlassifikation,
        DatumInSupervisor,
        DatumInExport,
        GETDATE()
    from inserted
end
GO
ALTER TABLE [dbo].[BatchTracking] ENABLE TRIGGER [t_InsertToStatisticFromBatchTracking]
GO
