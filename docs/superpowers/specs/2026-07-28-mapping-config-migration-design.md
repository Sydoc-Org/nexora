# Mapping-config migration — approaches (parked)

**Status: idea parked, no approach chosen yet.** Leaning A (YAML in git). Next concrete step is Phase 0 recon (read-only INT-vs-PROD diff) before committing to anything.

## Problem

The mapping of statistic tables and document-field columns lives in three NexoraDB tables, and the shape is unsatisfying:

- `dbo.StatConfig` — heap, no PK, all columns nullable. Per process (+ `ClientCode`): stat table name, export/import columns, extra condition, workitem column.
- `dbo.SearchConfig` — wide table, ~40 `col_*` columns (one per semantic doc-field), PK on `ProcessName` only. Adding a semantic field means a DDL migration for a new column.
- `dbo.IndexFieldMappings` (+ `dbo.Search_Field_Labels` for locale labels).

Observed pain:

- The app **never writes** these tables — they are read-only config, yet they live in a mutable per-environment store. Every change already goes through a git-reviewed SQL migration (14 migrations touch them: 0002, 0003, 0020, 0024, 0025, 0027, 0028, 0030, 0031, 0035, 0037, 0040) — worst of both worlds.
- Environment drift is possible and has bitten before (2026-07-20 STAGING doc-field flood was the "DB config differs per env" bug class).
- 8 app files hand-roll their own `SELECT ... FROM SearchConfig/Statconfig` (`workitems.py`, `dashboard.py`, `reporting.py`, `catalog.py`, `query.py`, `table_query.py`, `workitem_sources.py`, `process_helpers.py`), with the `SELECT TOP 0 *` column-introspection hack copy-pasted ~6 times and per-site caching.
- Bad mappings surface at query time, not boot time.

## Approach A — YAML in git (config-as-code) — recommended

Mappings move to `config/mappings/<client>.yaml` (e.g. `default.yaml`, `ms02.yaml`), loaded at startup into one typed registry module (`nx_lib/mapping_config.py`). All consumers read the registry. DB tables dropped once parity is proven.

Advantages:

- Every mapping change is a PR diff — reviewable, blame-able, one-commit revert (today the reviewer sees an `UPDATE` in a migration, not what the config now *is*).
- Env-drift bug class dies: same artifact on INT/STAGING/PROD.
- New semantic field = one YAML key + label. No DDL, no `col_*` column, no introspection hack.
- Zero config reads from NexoraDB at request time; no cache invalidation.
- Startup validation: schema-check the YAML, doctor-check "mapped column exists in target DB", fail loud at boot.

Disadvantages:

- Config change needs deploy + app-pool restart; no SSMS hot-fix. (Small real loss — PROD changes already ride migration + deploy.)
- If INT and PROD mappings legitimately differ, per-env override files must be designed (Phase 0 answers whether they differ at all).
- One-time migration cost (see estimate).
- A future admin-UI-for-mappings would fight this model.

## Approach B — normalize in DB

Wide `SearchConfig` → tall `ProcessFieldMapping(ProcessName, ClientCode, FieldKey, ColumnName)` + `ProcessSource(...)` with real PKs; DB stays authoritative; one shared accessor module.

Advantages: new field = INSERT not DDL; SSMS editability stays; natural path to an admin UI; smallest conceptual jump.

Disadvantages: env drift stays; config changes stay invisible to PR review; still runtime DB reads + query-time failure discovery; the 8 consumers need the accessor rewrite anyway — roughly the same effort as A with fewer wins.

## Approach C — hybrid (YAML truth → deploy-time sync into DB)

Git review + env parity like A, and mappings stay SQL-queryable. Rejected for now: most machinery (loader + sync + tables + "which is truth" ambiguity), SSMS edits silently vanish at next deploy, and **no external SQL consumer of these tables was found** — the only advantage over A serves nobody today.

## Common to all approaches

One accessor/registry module replaces the 8 scattered query sites. That part is not optional.

## Estimate for A

~4–6 focused days (≈ 1 plan session + 2–3 execute sessions):

- **Phase 0 — recon (0.5 d).** Export live rows from INT + PROD, diff. Only intentional per-env differences can grow the estimate, so this goes first. Read-only.
- **Phase 1 — registry (0.5–1 d).** Export script writes the YAML from live rows; `nx_lib/mapping_config.py` loads + schema-validates at startup. No consumer touched.
- **Phase 2 — consumer rewrite (2–3 d).** Swap all query sites for registry lookups (`workitems.py` + `dashboard.py` dominate: ~14 sites, ms02 partition logic, column whitelists). 8 test files (36 references) mock/seed these tables today — mocks get simpler (inject dict) but each needs touching.
- **Phase 3 — burn the ships (0.5 d).** Parity check on INT (registry output == old query output for all processes), migration drops the tables, docs + changelog, deploy-exclude check for the new config dir.

Phases 1–2 are shippable incrementally — the registry can co-exist with the tables until parity is proven; no big-bang cutover. Payoff starts immediately after: a new doc-field goes from "DDL migration + 6 file touches" to "one YAML line + label".
