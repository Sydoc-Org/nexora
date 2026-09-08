-- 0098: the mounted tenant Workitems page opens the list scoped to that tenant
-- (same shape as 0097 for the dashboard):
--   "query":  {"tenant": "<code>"}          -> /workitems?tenant=<code>
--   "active": "tenant_<code>_workitems"     -> only this entry lights up
-- Idempotent: rewrites the same values.

UPDATE dbo.TenantPages
   SET LayoutJSON = JSON_MODIFY(
                        JSON_MODIFY(LayoutJSON, '$.active', 'tenant_' + TenantCode + '_workitems'),
                        '$.query', JSON_QUERY('{"tenant":"' + TenantCode + '"}'))
 WHERE PageType = 'custom'
   AND ISJSON(LayoutJSON) = 1
   AND JSON_VALUE(LayoutJSON, '$.endpoint') = 'workitems_overview';
GO
