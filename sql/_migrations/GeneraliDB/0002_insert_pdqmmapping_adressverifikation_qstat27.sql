-- Seed PDQMMapping row: ParentCategory 'Adressverifikation' / SubCategory 'QSTAT 27'.
-- IF NOT EXISTS makes it safe to re-run (no unique constraint on these columns).

IF NOT EXISTS (
    SELECT 1 FROM dbo.PDQMMapping
    WHERE ParentCategory = N'Adressverifikation'
      AND SubCategory = N'QSTAT 27'
)
    INSERT INTO dbo.PDQMMapping (ParentCategory, SubCategory)
    VALUES (N'Adressverifikation', N'QSTAT 27');
GO
