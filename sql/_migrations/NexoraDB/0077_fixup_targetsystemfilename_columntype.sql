-- 0077: fixup -- revert ColumnType to NULL for a column whose NATIVE SQL Server
-- type is the deprecated `text` LOB type (#98 Task 12 live parity check on INT).
--
-- privera.02_InitialScan.targetsystemfilename maps to
-- dbo.PriveraInitialUndNeuzugaenge.init_Name, seeded by migration 0076 as
-- ColumnType = 'text' (matches Task 12's _TEXT_TYPES bucket). The parity check
-- comparing old-shape (CAST(...) AS NVARCHAR(MAX) COLLATE DATABASE_DEFAULT = ?)
-- against new-shape (bare column = ?) found this is not a mere collation
-- mismatch but a hard SQL Server error: native `text` columns do not support
-- the `=`/`<>` operators at all ("The data types text and nvarchar are
-- incompatible in the equal to operator.", error 402/8180). LIKE against the
-- bare column works fine, but the eq/neq bare-column path in
-- _docfield_predicate would break every eq/neq search on this field.
--
-- Reverting ColumnType to NULL keeps this column on the legacy CAST/COLLATE
-- fallback (always correct, just not sargable) until/unless the source table
-- migrates the column off `text` to varchar/nvarchar.
UPDATE dbo.ProcessFieldMappings
SET ColumnType = NULL
WHERE ClientCode = 'default'
  AND ProcessName = 'privera.02_InitialScan'
  AND FieldKey = 'targetsystemfilename';
GO
