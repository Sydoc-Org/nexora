-- 0068_relabel_backlog_total.sql
-- Two measures both labeled "Backlog" confused the wizard's step 1: the
-- legacy standalone one on the backlog_history source vs the new anchored
-- one on docprocessing (0067) that combines with imports/exports. The legacy
-- metric stays enabled (saved reports reference it) but is relabeled so the
-- pills explain themselves. Idempotent.

UPDATE dbo.ReportingMetrics
SET Label        = 'Backlog (detail analysis)',
    GermanLabel  = N'Backlog (Detailanalyse)',
    FrenchLabel  = N'Backlog (analyse détaillée)',
    ItalianLabel = N'Backlog (analisi dettagliata)'
WHERE Code = 'backlog_total' AND Label = 'Backlog';
GO
