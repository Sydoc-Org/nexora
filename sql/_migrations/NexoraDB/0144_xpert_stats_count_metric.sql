-- 0144_xpert_stats_count_metric.sql
-- Sydoc Finance (#408): the Xpert section lists BFH's and ZHAW's billed metrics
-- one by one (BFH Total / NeueKreditoren / Uebrige / UEReproduzierte, ZHAW
-- WorkItems / WorkItemsByEingang MAIL / WorkItemsByIsWithOrder 0 and 1).
-- dbo.Xpert_Stats already holds them as (Client, Metric, Dimension, Cnt) rows;
-- what is missing is a measure that sums Cnt without fixing the Metric, so the
-- page can group it by Metric and Dimension. The three 0128 measures each pin
-- one Metric and stay as they are.
--
-- Unfiltered on purpose: summed over every metric the number means nothing,
-- so it is only ever read grouped by Metric (nx_lib/finance.py). Idempotent.

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, FilterJson, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Filt, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('xpert_stats_count', 'xpert_stats', N'Count', N'Anzahl', N'Nombre', N'Conteggio',
        'sum', 'Cnt', NULL,
        N'Sum of Cnt over whatever metric rows are selected -- read it grouped by Metric', 'int', 323)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Filt, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
