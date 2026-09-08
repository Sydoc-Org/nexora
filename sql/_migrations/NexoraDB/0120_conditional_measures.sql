-- 0120_conditional_measures.sql
-- ReportingMetrics.FilterJson has existed since 0017 and nothing read it. The
-- semantic layer now turns it into CASE WHEN <cond> THEN ... END inside the
-- aggregate, so a KPI-style number ("reports filed on time") is one measure
-- instead of a breakdown the reader sums by eye. Shape: a JSON list of
-- {field, op, value} clauses ANDed together; ops eq/ne/gt/gte/lt/lte/in/not_in/
-- is_null/is_not_null; fields must be in the source's column catalog.
-- Seeds the three the Generali pages compute by hand. Idempotent.

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('generali_iss_ontime', 'generali_iss', N'Reports filed on time', N'Pünktlich eingereichte Reports', N'Rapports déposés à temps', N'Rapporti inviati puntualmente',
        'count', NULL, N'[{"field":"OnTime","op":"eq","value":true}]',
        N'ISS KPI reports filed with OnTime = 1', 'int', 141),
    ('generali_documents_nk_pass', 'generali_documents', N'Documents without post-check', N'Dokumente ohne Nachkontrolle', N'Documents sans post-contrôle', N'Documenti senza post-controllo',
        'count', NULL, N'[{"field":"DOC_NK1","op":"eq","value":"keineNachkontrolle"},{"field":"DOC_NK2","op":"eq","value":"keineNachkontrolle"}]',
        N'Documents where both post-checks are "keineNachkontrolle" (the dashboard KPI)', 'int', 102),
    ('generali_imports_failed', 'generali_imports', N'Failed runs', N'Fehlgeschlagene Läufe', N'Exécutions échouées', N'Esecuzioni fallite',
        'count', NULL, N'[{"field":"Status","op":"eq","value":"failed"}]',
        N'CSV import runs with Status = failed', 'int', 153)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
