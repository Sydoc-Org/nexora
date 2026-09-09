-- 0126_sydoc_mediamarkt_batches.sql
-- MediaMarkt scanning was counted in an Excel (Protokoll_MediaMarkt_<year>.xls,
-- one row per scanned batch). It moves into nexora as a generated Sydoc tenant
-- page over SYDOC_Statistik.dbo.MediaMarkt_Batches (created + back-filled by
-- C:\dev\nx-sources\mediamarkt\import_protocol.py; the stats DB is not
-- migration-tracked). Kind='entries' + PageType='crud' = the generic CRUD page,
-- no page code. Roles: Visum is 'person' (stamped from the login on every
-- write), Done / CorrectionsReceived are 'flag' (checkboxes) -- both generic
-- since this migration's companion code change.
-- The same table is a reporting source with Pieces / Batches measures.
-- Idempotent.

INSERT INTO dbo.TenantEntities
    (TenantCode, EntityKey, SourceObject, Kind, EngineRole, IdColumn, LabelEn, LabelDe, LabelFr, LabelIt, SortOrder, Status, ClientCode)
SELECT 'sydoc', 'mediamarkt', 'dbo.MediaMarkt_Batches', 'entries', 'stats', 'ID',
       N'MediaMarkt batches', N'MediaMarkt Batches', N'Lots MediaMarkt', N'Lotti MediaMarkt', 30, 'active', 'default'
WHERE NOT EXISTS (SELECT 1 FROM dbo.TenantEntities WHERE TenantCode = 'sydoc' AND EntityKey = 'mediamarkt');
GO

INSERT INTO dbo.TenantFields
    (TenantCode, EntityKey, ColumnName, SemanticRole, LabelEn, LabelDe, LabelFr, LabelIt, IsVisible, SortOrder, Status)
SELECT 'sydoc', 'mediamarkt', v.Col, v.Role, v.En, v.De, v.Fr, v.It, 1, v.Ord, 'active'
FROM (VALUES
    ('ScanDate',            'date',     N'Date',                 N'Datum',               N'Date',                   N'Data',                   10),
    ('BatchNo',             'identifier', N'Batch',              N'Batch',               N'Lot',                    N'Lotto',                  20),
    ('Pieces',              'count',    N'Pieces',               N'Stückzahl',           N'Pièces',                 N'Pezzi',                  30),
    ('DocType',             'category', N'Type (K/D/KA)',        N'Kred, Deb, KA',       N'Type (K/D/KA)',          N'Tipo (K/D/KA)',          40),
    ('Done',                'flag',     N'Done',                 N'Erledigt',            N'Terminé',                N'Completato',             50),
    ('CorrectionBatches',   'text',     N'Correction batches',   N'Korr Batch',          N'Lots de correction',     N'Lotti di correzione',    60),
    ('Corrections',         'count',    N'Corrections',          N'Anzahl Korr',         N'Corrections',            N'Correzioni',             70),
    ('CorrectionsReceived', 'flag',     N'Corrections received', N'Korr erhalten',       N'Corrections reçues',     N'Correzioni ricevute',    80),
    ('Remarks',             'text',     N'Remarks',              N'Bemerkungen',         N'Remarques',              N'Osservazioni',           90),
    ('Visum',               'person',   N'Visum',                N'Visum',               N'Visa',                   N'Visto',                  100)
) AS v(Col, Role, En, De, Fr, It, Ord)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.TenantFields tf
    WHERE tf.TenantCode = 'sydoc' AND tf.EntityKey = 'mediamarkt' AND tf.ColumnName = v.Col
);
GO

INSERT INTO dbo.TenantPages (TenantCode, PageKey, PageType, EntityKey, LayoutJSON, SortOrder, Status)
SELECT 'sydoc', 'mediamarkt', 'crud', 'mediamarkt', NULL, 30, 'active'
WHERE NOT EXISTS (SELECT 1 FROM dbo.TenantPages WHERE TenantCode = 'sydoc' AND PageKey = 'mediamarkt');
GO

INSERT INTO dbo.Permission (Code, Description)
SELECT N'reporting.source.mediamarkt_batches.use', N'Use the MediaMarkt Batches source'
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission WHERE Code = N'reporting.source.mediamarkt_batches.use');
GO

IF NOT EXISTS (SELECT 1 FROM dbo.ReportingSources WHERE Code = 'mediamarkt_batches')
INSERT INTO dbo.ReportingSources
    (Code, Kind, Label, Permission, Engine, Provider, BaseObject, ColumnsJSON, Enabled, SortOrder)
VALUES (
    'mediamarkt_batches', 'curated', N'MediaMarkt — Batches',
    'reporting.source.mediamarkt_batches.use', 'statistics', 'table', 'dbo.MediaMarkt_Batches',
    N'[{"field":"ScanDate","label":"Date","type":"date","filterable":true,"sortable":true,"grainable":true},
       {"field":"BatchNo","label":"Batch","type":"number","filterable":true,"sortable":true},
       {"field":"Pieces","label":"Pieces","type":"number","filterable":true,"sortable":true},
       {"field":"DocType","label":"Type (K/D/KA)","type":"string","filterable":true,"sortable":true},
       {"field":"Done","label":"Done (1/0)","type":"number","filterable":true,"sortable":true},
       {"field":"Corrections","label":"Corrections","type":"number","filterable":true,"sortable":true},
       {"field":"CorrectionsReceived","label":"Corrections received (1/0)","type":"number","filterable":true,"sortable":true},
       {"field":"Visum","label":"Visum","type":"string","filterable":true,"sortable":true},
       {"field":"Remarks","label":"Remarks","type":"string","filterable":true,"sortable":false}]',
    1, 320);
GO

INSERT INTO dbo.ReportingMetrics
    (Code, SourceId, Label, GermanLabel, FrenchLabel, ItalianLabel, Aggregation, BaseField, Description, Format, SortOrder)
SELECT v.Code, v.SourceId, v.Label, v.De, v.Fr, v.It, v.Agg, v.BaseField, v.Descr, v.Fmt, v.SortOrder
FROM (VALUES
    ('mediamarkt_pieces',  'mediamarkt_batches', N'Pieces scanned', N'Gescannte Stücke', N'Pièces numérisées', N'Pezzi scansionati',
        'sum',   'Pieces', N'Sum of pieces per scanned MediaMarkt batch', 'int', 320),
    ('mediamarkt_batches', 'mediamarkt_batches', N'Batches',        N'Batches',          N'Lots',              N'Lotti',
        'count', NULL,     N'Number of MediaMarkt batches',              'int', 321)
) AS v(Code, SourceId, Label, De, Fr, It, Agg, BaseField, Descr, Fmt, SortOrder)
WHERE NOT EXISTS (SELECT 1 FROM dbo.ReportingMetrics m WHERE m.Code = v.Code);
GO
