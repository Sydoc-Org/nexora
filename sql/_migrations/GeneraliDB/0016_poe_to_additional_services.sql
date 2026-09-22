-- POE moves from Basisleistungen to Zusatzleistungen, effective 2026-10-01.
--
-- Requested by Generali (Alldin, clarified by Giusi, September 2026): from
-- 1 October they report POE hours under Zusatzleistungen (Additional
-- Services) instead of Basisleistungen (Base Services).
--
-- POE is a PARENT category with no subcategory. That is a shape the page
-- already handles and already ships: 'PDQM' and 'Weitere Taetigkeiten' are
-- both stored the same way, with SubCategory NULL, and the Additional
-- Services page renders an em-dash in the subcategory dropdown and disables
-- it (see the `subs.length === 0` branch in
-- templates/js/_generali_additional_services_js.html).
--
-- No dbo.CategoryTerms row is added, deliberately. That table exists for
-- terms whose German label differs per locale; the page falls back to the
-- German term when a lookup misses (`translationsMap[parent] || parent`),
-- and "POE" is the same string in de, en, fr and it. A row here would be a
-- row to keep in step for no gain.
--
-- The other half of this change is NOT in SQL. Base Services keeps its
-- category list hardcoded in templates/js/_generali_base_services_js.html,
-- where POE moves from BASE_CATEGORIES to LEGACY_CATEGORIES -- no longer
-- bookable, still filterable, so hours booked before 1 October stay visible
-- in the list and in the month report.
--
-- TIMING. This takes effect on PROD when someone pushes a `v*` tag, not when
-- it merges. Tag at the end of September: tagging earlier removes POE from
-- Basisleistungen while people are still booking September hours there.
--
-- Idempotent. Note that SQL Server's `=` ignores trailing whitespace, so the
-- guard also matches a stray 'POE ' -- which is the intent here, and is the
-- same trailing-space trap migration 0015 cleaned up.

IF NOT EXISTS (
    SELECT 1 FROM [dbo].[EffortCategories]
    WHERE [ParentCategory] = N'POE' AND [SubCategory] IS NULL
)
BEGIN
    INSERT INTO [dbo].[EffortCategories] ([ParentCategory], [SubCategory])
    VALUES (N'POE', NULL);
END
GO
