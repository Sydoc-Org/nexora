DECLARE @FileID int = 10000
WHILE(@FileID <= 10012)
BEGIN
    INSERT INTO StadtBiel
    VALUES('SB' + CONVERT(nvarchar, @FileID), 'SB_Baugesuche_' + CONVERT(nvarchar, @FileID), 
    'D:\Sydoc\StadtBiel\Done\' + 'SB_Baugesuche_' + CONVERT(nvarchar, @FileID), 'Done', null, GETDATE())
    SET @FileID = @FileID + 1
END

SELECT TOP (1000) [SBID]
      ,[FileID]
      ,[FileName]
      ,[FilePath]
      ,[State]
      ,[DemandedBy]
      ,[DateTime]
  FROM [SYDOC_Statistik].[dbo].[StadtBiel]