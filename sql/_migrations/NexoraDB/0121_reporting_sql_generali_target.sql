-- 0121_reporting_sql_generali_target.sql
--
-- Live SQL gains a third target: the Generali tenant database, so the sandbox
-- covers every database the Sources rail lists a card for (RuntimeDatabase,
-- SYDOC_Statistik, Generali). NexoraDB is deliberately NOT a target -- it holds
-- the bcrypt password hashes and TOTP secrets.
--
-- Follows the per-target grammar from 0088: the base reporting.sql.run gate
-- covers Statistics, and every other database needs its own grant on top, so
-- SQL access and access to a particular database stay separable. The Enterprise
-- Admin trigger (0106) grants the new code; nobody else gets it implicitly.
--
-- The target answers 503 until DB_REPORTING_GENERALI_RO_* is provisioned on the
-- box -- see scripts/provision-reporting-ro-logins.sql and
-- docs/howto/reporting.md -> "Owner setup".
--
-- Idempotent.

INSERT INTO dbo.Permission (Code, Description)
SELECT v.Code, v.Descr
FROM (VALUES
    (N'reporting.sql.target.generali.use', N'Target the Generali tenant DB in the sandbox')
) AS v(Code, Descr)
WHERE NOT EXISTS (SELECT 1 FROM dbo.Permission p WHERE p.Code = v.Code);
GO
