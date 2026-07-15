-- 0039_metric_labels_and_page_count.sql
-- Localized labels for canonical metrics + the "Pages processed" metric.
--
-- dbo.ReportingMetrics gains German/French/Italian label columns (mirrors
-- Search_Field_Labels: NULL falls back to the English Label). Backfills the
-- two existing rows and seeds page_count = SUM(pagecount) on docprocessing.
-- The query builder projects sum/avg bases as TRY_CAST(col AS float), so a
-- non-numeric cell or a process without col_pagecount contributes NULL --
-- i.e. nothing -- to the sum. Idempotent.

IF COL_LENGTH(N'dbo.ReportingMetrics', N'GermanLabel') IS NULL
BEGIN
    ALTER TABLE dbo.ReportingMetrics ADD
        GermanLabel  NVARCHAR(120) NULL,
        FrenchLabel  NVARCHAR(120) NULL,
        ItalianLabel NVARCHAR(120) NULL;
END;
GO

UPDATE dbo.ReportingMetrics
SET GermanLabel  = N'Anzahl Dokumente',
    FrenchLabel  = N'Nombre de documents',
    ItalianLabel = N'Numero di documenti'
WHERE Code = 'doc_count' AND GermanLabel IS NULL;

UPDATE dbo.ReportingMetrics
SET GermanLabel  = N'Anzahl Workitems (eindeutig)',
    FrenchLabel  = N'Nombre de workitems (distincts)',
    ItalianLabel = N'Numero di workitem (distinti)'
WHERE Code = 'workitem_count' AND GermanLabel IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'page_count')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder)
    VALUES
        ('page_count', 'docprocessing', 'Pages processed',
         N'Verarbeitete Seiten', N'Pages traitées', N'Pagine elaborate',
         'sum', 'pagecount',
         'Total scanned pages in scope (sum of the per-document page count; only processes with a mapped pagecount field contribute)',
         'int', 30);
GO
