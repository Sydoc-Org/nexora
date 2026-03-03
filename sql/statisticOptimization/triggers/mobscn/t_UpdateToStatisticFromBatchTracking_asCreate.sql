SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[t_UpdateToStatisticFromBatchTracking] on [dbo].[BatchTracking]
FOR UPDATE
as
begin
    UPDATE SYDOC_Statistik.dbo.MOBSCN_CLIENT
    SET 
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.PID = inserted.PID,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.ScanBatchNr = inserted.ScanBatchNr,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.ScanArchivBoxNr = inserted.ScanArchivBoxNr,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.ScanDatum = inserted.ScanDatum,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumImportiert = inserted.DatumImportiert,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumInSplitting = inserted.DatumInSplitting,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumInKlassifikation = inserted.DatumInKlassifikation,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumInSupervisor = inserted.DatumInSupervisor,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumInExport = inserted.DatumInExport,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.UpdatedAt = GETDATE()
    FROM inserted
    WHERE inserted.WorkItemID = SYDOC_Statistik.dbo.MOBSCN_CLIENT.WorkitemID
end
GO
ALTER TABLE [dbo].[BatchTracking] ENABLE TRIGGER [t_UpdateToStatisticFromBatchTracking]
GO
