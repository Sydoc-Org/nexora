-- 0052_fix_vat_client_index_field_mapping.sql
-- Workitem details showed the wrong MWST (reported on PROD; INT had the same
-- rows): two dbo.IndexFieldMappings rows carried swapped TargetKeys --
--   'RptCompCode' -> 'VatAmount'  (company code rendered as "MWST. Betrag")
--   'VatAmount'   -> 'Client'     (duplicate source name; get_index_field_mappings
--                                  keys the dict by SourceFieldName so this row
--                                  overrode the correct 'VatAmount' -> 'VatAmount'
--                                  mapping and the real VAT surfaced as "Mandant")
-- Intended mapping is RptCompCode -> Client; the duplicate VatAmount row is
-- removed outright ('VatAmount' -> 'VatAmount' already exists).

UPDATE dbo.IndexFieldMappings
SET TargetKey = 'Client'
WHERE SourceFieldName = 'RptCompCode' AND TargetKey = 'VatAmount';
GO

DELETE FROM dbo.IndexFieldMappings
WHERE SourceFieldName = 'VatAmount' AND TargetKey = 'Client';
GO
