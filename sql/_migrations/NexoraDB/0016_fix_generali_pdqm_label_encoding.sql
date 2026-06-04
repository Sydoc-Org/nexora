-- 0016_fix_generali_pdqm_label_encoding.sql
-- Repair the mojibake 'generali_pdqm' source label.
--
-- Migration 0011 seeded the label 'Generali — PDQM Report' (em-dash U+2014) as
-- correct UTF-8 in the .sql file, but db-migrate.py applied it through sqlcmd
-- WITHOUT a UTF-8 input codepage, so sqlcmd read the em-dash bytes in the host
-- OEM/ANSI codepage and stored the double-mojibake "Generali â€" PDQM Report"
-- (codepoints U+00E2 U+20AC U+201D) into dbo.ReportingSources.Label — visible in
-- the Reporting source dropdown. db-migrate.py is now fixed (sqlcmd -f 65001);
-- this corrects the row already stored. NCHAR(0x2014) builds the em-dash from its
-- code point, so this migration is itself immune to the codepage bug regardless
-- of how it is applied. Idempotent (no-op once the label is correct).
UPDATE dbo.ReportingSources
SET Label = N'Generali ' + NCHAR(0x2014) + N' PDQM Report'
WHERE Code = 'generali_pdqm'
  AND Label <> N'Generali ' + NCHAR(0x2014) + N' PDQM Report';
GO
