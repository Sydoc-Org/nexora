SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[t_UpdateToStatisticFromBatchTracking] on [dbo].[BatchTracking]
FOR UPDATE
as
begin
    UPDATE SYDOC_Statistik.dbo.BankWIR
    SET 
        SYDOC_Statistik.dbo.BankWIR.PID = inserted.PID,
        SYDOC_Statistik.dbo.BankWIR.ScanBatchNr = inserted.ScanBatchNr,
        SYDOC_Statistik.dbo.BankWIR.ScanArchivBoxNr = inserted.ScanArchivBoxNr,
        SYDOC_Statistik.dbo.BankWIR.ScanDatum = inserted.ScanDatum,
        SYDOC_Statistik.dbo.BankWIR.DatumImportiert = inserted.DatumImportiert,
        SYDOC_Statistik.dbo.BankWIR.DatumInSplitting = inserted.DatumInSplitting,
        SYDOC_Statistik.dbo.BankWIR.DatumInKlassifikation = inserted.DatumInKlassifikation,
        SYDOC_Statistik.dbo.BankWIR.DatumInSupervisor = inserted.DatumInSupervisor,
        SYDOC_Statistik.dbo.BankWIR.DatumInExport = inserted.DatumInExport,
        SYDOC_Statistik.dbo.BankWIR.UpdatedAt = GETDATE()
    FROM inserted
    WHERE inserted.WorkItemID = SYDOC_Statistik.dbo.BankWIR.WorkitemID
end
GO
ALTER TABLE [dbo].[BatchTracking] ENABLE TRIGGER [t_UpdateToStatisticFromBatchTracking]
GO
