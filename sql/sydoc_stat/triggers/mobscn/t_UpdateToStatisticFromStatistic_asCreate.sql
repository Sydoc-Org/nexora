SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
CREATE TRIGGER [dbo].[t_UpdateToStatisticFromStatistic] on [dbo].[Statistik]
FOR UPDATE, INSERT
as
begin
    UPDATE SYDOC_Statistik.dbo.MOBSCN_CLIENT
    SET 
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DatumLieferung = inserted.DatumLieferung,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.PersonenAkteID = inserted.PersonenAkteID,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.AnstellungsAkteID = inserted.AnstellungsAkteID,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DokArtIDZielsystem = inserted.DokArtIDZielsystem,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DokArtIDSydoc = inserted.DokArtIDSydoc,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DokArtName = inserted.DokArtName,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.DokDatum = inserted.DokDatum,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.RegisterIDZielsystem = inserted.RegisterIDZielsystem,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.StammdatenDeckblattTyp = inserted.StammdatenDeckblattTyp,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.StammdatenGeburtsdatum = inserted.StammdatenGeburtsdatum,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.StammdatenVorname = inserted.StammdatenVorname,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.StammdatenNachname = inserted.StammdatenNachname,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.StammdatenTrennblattID = inserted.StammdatenTrennblattID,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.ZielsystemDateiname = inserted.ZielsystemDateiname,
        SYDOC_Statistik.dbo.MOBSCN_CLIENT.UpdatedAt = GETDATE()
    FROM inserted
    WHERE inserted.WorkItemID = SYDOC_Statistik.dbo.MOBSCN_CLIENT.WorkitemID
end
GO
ALTER TABLE [dbo].[Statistik] ENABLE TRIGGER [t_UpdateToStatisticFromStatistic]
GO
