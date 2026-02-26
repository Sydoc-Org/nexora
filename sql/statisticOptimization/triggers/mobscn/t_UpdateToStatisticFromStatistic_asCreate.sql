SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[t_UpdateToStatisticFromStatistic] on [dbo].[Statistik]
FOR UPDATE, INSERT
as
begin
    UPDATE SYDOC_Statistik.dbo.BankWIR
    SET 
        SYDOC_Statistik.dbo.BankWIR.DatumLieferung = inserted.DatumLieferung,
        SYDOC_Statistik.dbo.BankWIR.PersonenAkteID = inserted.PersonenAkteID,
        SYDOC_Statistik.dbo.BankWIR.AnstellungsAkteID = inserted.AnstellungsAkteID,
        SYDOC_Statistik.dbo.BankWIR.DokArtIDZielsystem = inserted.DokArtIDZielsystem,
        SYDOC_Statistik.dbo.BankWIR.DokArtIDSydoc = inserted.DokArtIDSydoc,
        SYDOC_Statistik.dbo.BankWIR.DokArtName = inserted.DokArtName,
        SYDOC_Statistik.dbo.BankWIR.DokDatum = inserted.DokDatum,
        SYDOC_Statistik.dbo.BankWIR.RegisterIDZielsystem = inserted.RegisterIDZielsystem,
        SYDOC_Statistik.dbo.BankWIR.StammdatenDeckblattTyp = inserted.StammdatenDeckblattTyp,
        SYDOC_Statistik.dbo.BankWIR.StammdatenGeburtsdatum = inserted.StammdatenGeburtsdatum,
        SYDOC_Statistik.dbo.BankWIR.StammdatenVorname = inserted.StammdatenVorname,
        SYDOC_Statistik.dbo.BankWIR.StammdatenNachname = inserted.StammdatenNachname,
        SYDOC_Statistik.dbo.BankWIR.StammdatenTrennblattID = inserted.StammdatenTrennblattID,
        SYDOC_Statistik.dbo.BankWIR.ZielsystemDateiname = inserted.ZielsystemDateiname,
        SYDOC_Statistik.dbo.BankWIR.UpdatedAt = GETDATE()
    FROM inserted
    WHERE inserted.WorkItemID = SYDOC_Statistik.dbo.BankWIR.WorkitemID
end
GO
ALTER TABLE [dbo].[Statistik] ENABLE TRIGGER [t_UpdateToStatisticFromStatistic]
GO
