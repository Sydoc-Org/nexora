-- 0097: the mounted tenant Dashboard opens the dashboard scoped to that tenant.
--
-- A custom page that points at the global 'dashboard' endpoint gains
--   "query":  {"tenant": "<code>"}          -> /dashboard?tenant=<code>
--   "active": "tenant_<code>_dashboard"     -> only this entry lights up
-- The dashboard view stores the tenant in the session and narrows the user's
-- dashboard.filter.process.* grants to the processes whose organization
-- belongs to the tenant. Generali's page targets its own generali-dashboard
-- endpoint and is untouched. Idempotent: rewrites the same values.

UPDATE dbo.TenantPages
   SET LayoutJSON = JSON_MODIFY(
                        JSON_MODIFY(LayoutJSON, '$.active', 'tenant_' + TenantCode + '_dashboard'),
                        '$.query', JSON_QUERY('{"tenant":"' + TenantCode + '"}'))
 WHERE PageType = 'custom'
   AND ISJSON(LayoutJSON) = 1
   AND JSON_VALUE(LayoutJSON, '$.endpoint') = 'dashboard';
GO
