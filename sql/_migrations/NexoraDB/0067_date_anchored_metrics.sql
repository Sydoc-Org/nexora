-- 0067_date_anchored_metrics.sql
-- Date-anchored measures: "documents/pages imported" count on the import
-- date, "documents/pages exported" on the export date, "Backlog" reads
-- dbo.BacklogHistory — all plotted on ONE shared time axis (the synthetic
-- activity_date catalog field), so one report shows the import line, the
-- export line and the backlog line together. DateAnchor tells the query
-- builder which date drives each metric's leg; NULL = ordinary metric.
-- Idempotent.

IF COL_LENGTH(N'dbo.ReportingMetrics', N'DateAnchor') IS NULL
    ALTER TABLE dbo.ReportingMetrics ADD DateAnchor NVARCHAR(32) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'docs_imported')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder, DateAnchor)
    VALUES
        ('docs_imported', 'docprocessing', 'Documents imported',
         N'Dokumente importiert', N'Documents importés', N'Documenti importati',
         'sum', NULL,
         'Documents counted on their import date (anchored; plots on the shared activity_date axis)',
         'int', 12, 'import_date');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'docs_exported')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder, DateAnchor)
    VALUES
        ('docs_exported', 'docprocessing', 'Documents exported',
         N'Dokumente exportiert', N'Documents exportés', N'Documenti esportati',
         'sum', NULL,
         'Documents counted on their export date (anchored; plots on the shared activity_date axis)',
         'int', 14, 'export_date');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'pages_imported')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder, DateAnchor)
    VALUES
        ('pages_imported', 'docprocessing', 'Pages imported',
         N'Seiten importiert', N'Pages importées', N'Pagine importate',
         'sum', 'pagecount',
         'Page counts summed on the document''s import date (anchored; only processes with a mapped pagecount field contribute)',
         'int', 32, 'import_date');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'pages_exported')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder, DateAnchor)
    VALUES
        ('pages_exported', 'docprocessing', 'Pages exported',
         N'Seiten exportiert', N'Pages exportées', N'Pagine esportate',
         'sum', 'pagecount',
         'Page counts summed on the document''s export date (anchored; only processes with a mapped pagecount field contribute)',
         'int', 34, 'export_date');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics WHERE Code = 'backlog')
    INSERT INTO dbo.ReportingMetrics
        (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel,
         Aggregation, BaseField, Description, Format, SortOrder, DateAnchor)
    VALUES
        ('backlog', 'docprocessing', 'Backlog',
         N'Backlog', N'Backlog', N'Backlog',
         'sum', NULL,
         'Point-in-time backlog from dbo.BacklogHistory (newest snapshot per bucket), scoped to the report''s processes; plots on the shared activity_date axis',
         'int', 42, 'backlog');
GO
