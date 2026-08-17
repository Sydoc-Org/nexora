-- 0056: archive the invoices page (#177).
-- dbo.ClientInvoices only ever fed nx_lib/views/invoices.py (bexio client-id
-- lookup). That page is retired: its routes are no longer registered, so the
-- table has no reader left. Renamed rather than dropped — data preserved and
-- the change is reversible with a single sp_rename back.
--
-- Same convention as 0042 (decapitated_ prefix). Idempotent: guarded on
-- OBJECT_ID(old) IS NOT NULL AND OBJECT_ID(new) IS NULL so the pre-commit hook
-- can re-apply it. sp_rename's second argument MUST be the BARE new name.
--
-- The invoices.* permission rows in dbo.Permission are deliberately left alone
-- so an admin can still see the historical grants.
IF OBJECT_ID(N'dbo.ClientInvoices', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.decapitated_ClientInvoices', N'U') IS NULL
    EXEC sp_rename N'dbo.ClientInvoices', N'decapitated_ClientInvoices';
GO
