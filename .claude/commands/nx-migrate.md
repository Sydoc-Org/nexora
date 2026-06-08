---
description: Scaffold the next nexora SQL migration file (sql/_migrations/<Db>/NNNN_*.sql)
argument-hint: "<NexoraDB|GeneraliDB> <short_snake_description>"
---

Scaffold a new nexora schema migration. Arguments: `$1` = database (`NexoraDB` or `GeneraliDB`), the rest = a short snake_case description. Reference: `docs/howto/db-migrations.md` (2.5.63+) and the "Databases" section of `CLAUDE.md`.

Steps:

1. **Pick the number.** List `sql/_migrations/$1/`, take the highest `NNNN_` prefix, add 1, zero-pad to 4 digits. If `$1` is missing or not one of `NexoraDB` / `GeneraliDB`, ask which (only those two app-owned DBs are tracked — never `StatisticsDB`/`OctoDB`).
2. **Create** `sql/_migrations/$1/NNNN_<description>.sql` with a one-line header comment stating what it does, then one or more SQL batches separated by `GO`. Prefer **idempotent** guards (`IF NOT EXISTS (…)`, `IF COL_LENGTH(…) IS NULL`, `IF OBJECT_ID(…) IS NULL`) so the pre-commit hook can re-apply it safely without `--mark-applied`.
3. **Do not** touch anything under `sql/$1/<Object>/…` — those per-object DDL files are auto-generated from INT.
4. **Explain the apply flow — don't run it blindly.** Committing auto-applies pending migrations to INT via the pre-commit hook and re-dumps the per-object DDL. If you already ran the statements in SSMS while prototyping, record them first so the hook doesn't re-apply: `python scripts/db-migrate.py --env INT --mark-applied`. PROD is applied by the deploy workflow before the app pool stops, or ad-hoc via `python scripts/db-migrate.py --env PROD`. If the hook can't reach INT, `SQL_SYNC_SKIP=1 git commit` (never `--no-verify`).
5. **Changelog.** Add a matching `[Unreleased]` entry in `CHANGELOG.md`.

Migrations are immutable once applied — to undo or alter one, add a **new** migration, never edit the old file.
