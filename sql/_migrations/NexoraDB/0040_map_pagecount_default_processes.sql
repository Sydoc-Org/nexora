-- 0040_map_pagecount_default_processes.sql
-- Map SearchConfig.col_pagecount for the five default-client processes so the
-- page_count metric ("Pages processed", seeded by 0039) returns numbers for
-- them — until now only sydoc.05_PDBS (ms02) was mapped (0030).
--
-- Column names verified against the live INT statistics tables; Seiten is
-- NVARCHAR, which is fine: the query builder projects sum bases as
-- TRY_CAST(col AS float), so non-numeric cells contribute NULL (nothing).
-- Idempotent: only fills rows whose col_pagecount is still NULL.

UPDATE dbo.SearchConfig SET col_pagecount = 'AnzImagesOut'
WHERE ProcessName = 'compass.01_Invoice_SAP' AND ClientCode = 'default' AND col_pagecount IS NULL;

UPDATE dbo.SearchConfig SET col_pagecount = 'AnzImagesOut'
WHERE ProcessName = 'elektromaterial.02_Invoice' AND ClientCode = 'default' AND col_pagecount IS NULL;

UPDATE dbo.SearchConfig SET col_pagecount = 'Seiten'
WHERE ProcessName = 'privera.02_InitialScan' AND ClientCode = 'default' AND col_pagecount IS NULL;

UPDATE dbo.SearchConfig SET col_pagecount = 'AnzahlImagesProcessed'
WHERE ProcessName = 'privera.02_Posteingang' AND ClientCode = 'default' AND col_pagecount IS NULL;

UPDATE dbo.SearchConfig SET col_pagecount = 'AnzImagesScanned'
WHERE ProcessName = 'privera.03_Invoice_New' AND ClientCode = 'default' AND col_pagecount IS NULL;
GO
