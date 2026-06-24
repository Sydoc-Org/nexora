-- 0027_searchconfig_ms02_docfields.sql
-- Make dbo.SearchConfig source/dialect-aware so doc-field search can route
-- between the default StatisticsDB (columnar) and the MS02 doc-field DB (EAV).
-- Mirrors dbo.Statconfig.ClientCode (migration 0024).
--
-- (1) ADD ClientCode: which client/dialect a SearchConfig row belongs to.
--     'default' rows -> col_<field> is a StatisticsDB physical COLUMN name,
--     resolved as `CAST(alias.col AS NVARCHAR(MAX)) LIKE ?` on engine_statistics_db.
--     'ms02'    rows -> col_<field> is an EAV "Name" VALUE, resolved as
--     `WHERE "Name" = <col_field> AND "StringValue" LIKE %value%` on
--     engine_ms02_docfields_pg (a SEPARATE Postgres DB). The DEFAULT 'default'
--     keeps every existing row behaving exactly as today (byte-identical path).
--     NOT prefixed 'col_' on purpose: get_valid_search_columns() only picks up
--     'col_'-prefixed columns, so ClientCode is ignored by the field enumerator.
--
-- (2) Seed MS02 SearchConfig row(s). OWNER-PROVIDED build-time values (see the
--     plan's Owner-actions section) -- DO NOT guess:
--       * ProcessName MUST be the '<client>.<process>' key target_processes
--         carries (e.g. 'sydoc.praesidialdepartement_bs', same key as the 0025
--         Statconfig seed). Wrong key => the resolver finds no config and
--         (graceful-degrade) imposes NO doc-field constraint, silently
--         returning ALL rows.
--       * For an EAV row, TableName/TableAlias/JoinCondition/TimeFilter/
--         SuggestionTimeFilter are columnar-StatisticsDB semantics and are
--         MEANINGLESS for MS02 -- leave them NULL; the EAV resolver ignores
--         them and uses engine_ms02_docfields_pg.
--       * Each col_<field> value holds the doc-field "Name" string to match in
--         the EAV index (e.g. col_docbarcode = 'Barcode'), NOT a column name.
--         col_<field> is varchar(100): confirm each EAV "Name" fits (Owner #6).
--     Fill the col_<field> -> EAV-Name mappings the MS02 search UI exposes, then
--     uncomment.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.SearchConfig') AND name = 'ClientCode'
)
BEGIN
    ALTER TABLE dbo.SearchConfig
        ADD ClientCode NVARCHAR(50) NOT NULL
        CONSTRAINT DF_SearchConfig_ClientCode DEFAULT 'default';
END
GO

-- MS02 doc-field mapping row. Columnar columns stay NULL (EAV resolution does
-- not join StatisticsDB). Each col_<field> = the doc-field "Name" to match.
-- OWNER: fill the col_<field> -> "Name" values, then uncomment the ENTIRE
-- block below (the IF/BEGIN guard through the closing GO) -- NOT just the
-- INSERT, or it would run unconditionally:
-- IF NOT EXISTS (SELECT 1 FROM dbo.SearchConfig WHERE ProcessName = 'sydoc.praesidialdepartement_bs')
-- BEGIN
--     INSERT INTO dbo.SearchConfig
--         (ProcessName, TableName, TableAlias, JoinCondition, TimeFilter,
--          SuggestionTimeFilter, ClientCode, col_docbarcode /*, col_<field> ... */)
--     VALUES
--         ('sydoc.praesidialdepartement_bs', NULL, NULL, NULL, NULL,
--          NULL, 'ms02', 'Barcode' /*, '<EAV Name>' ... */);
-- END
-- GO
