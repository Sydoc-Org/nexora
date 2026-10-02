-- 0143_finance_bexio_contact_links.sql  (#423)
-- Link every Finance client to its Bexio contact(s) once, so nobody has to
-- link them by hand on each environment. The panel only shows invoices to
-- linked contacts, so these rows decide what it lists.
--
-- Contact ids are Bexio's own (Sydoc's single Bexio account), read on
-- 2026-10-01 from the invoices of 2025-2026. Aveniq is billed both as
-- Aveniq AG and as Xpert Consulting AG.
--
-- Idempotent: a contact that is already linked keeps its link.

INSERT INTO dbo.FinanceBexioContacts (ContactId, Client, LinkedBy)
SELECT v.ContactId, v.Client, N'migration 0143'
FROM (VALUES
    (247, N'Elektro-Material'),   -- EM Elektro-Material
    (399, N'Compass Group'),      -- Compass Group (Schweiz) AG
    (294, N'Privera'),            -- Privera AG
    (460, N'Frigemo'),            -- frigemo AG
    (223, N'Aveniq'),             -- Aveniq AG
    (755, N'Aveniq'),             -- Xpert Consulting AG
    (238, N'Bucherer'),           -- Bucherer AG
    (409, N'MediaMarkt')          -- Media Markt Schweiz AG, Rechnungswesen
) AS v (ContactId, Client)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.FinanceBexioContacts c WHERE c.ContactId = v.ContactId
);
GO
