# Generali DB restructure — English names, one style, better logic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan phase-by-phase. Steps use checkbox (`- [ ]`) syntax. Every table, column, row count and fill rate quoted below was **measured against the live INT `Generali` database on 2026-08-27** (`sys.*` catalogs + a full profiling pass over 2,468,923 `ReportJob` rows) — re-measure before executing, the importer runs daily. Plan file: `docs/superpowers/plans/2026-08-27-generali-db-restructure.md`.

**Issue:** [#220](https://github.com/Sydoc-Code/nexora/issues/220) — the four open questions at the bottom of this plan are repeated there for the owner to answer.

**Goal:** Turn the Generali tenant DB from a half-German, half-English, string-typed CSV landing zone into a schema someone can read: **English names, one naming style, real types, real keys, real indexes** — without a single minute of downtime for `/generali/*` or the daily CSV import.

**Why now:** the reporting source visualizer (`reporting.sources.schema`, shipped 2026-08-27) draws this database, and it draws it honestly: one 79-column table whose columns are `DOC_SCHADEN_NR`-style SCREAMING_SNAKE German, thirteen two-column German lookup tables, four near-identical effort-logging tables, and a `PDQMReport` table with **5 rows** that the reporting registry points at while the 2.47M-row table beside it is what actually holds the data.

**Architecture:** Six phases, each one migration + the code that goes with it, each independently shippable and independently revertible. Renames are `sp_rename` (metadata-only — instant on 2.47M rows, no data copy); every rename ships **with a compatibility view under the old name in the same migration**, because `deploy.yml` applies migrations *before* it stops the app pool, so old code and new schema overlap by seconds on every deploy. The compat views come out one release later.

**Tech stack:** T-SQL migrations in `sql/_migrations/GeneraliDB/` (applied by `scripts/db-migrate.py`, auto-applied to INT by the `sql-migrate-int` pre-commit hook, to PROD by `deploy.yml`), pyodbc via `engine_generali_db`, and the PowerShell importer under `scripts/generali-import/`. **The single `nx_lib/views/generali.py` this plan was written against is now a package** — `nx_lib/views/generali/{__init__,_crud,_scope,attendance,baseservices,documents,importstatus,pdqm,projectmanagement,reporting}.py`. All 12 `v_ReportJobJoinDefinitions` references live in `documents.py`; the effort-table CRUD is in `_crud.py` plus the four page modules. Every line reference below to `generali.py` needs re-locating in the package.

---

## Context an engineer needs (read first)

- **Branch:** cut from `v3.2.3.1`. Parallel sessions are normal here — work in your own worktree (`git worktree add .claude/worktrees/generali-db -b feat/generali-db-restructure v3.2.3.1`), stage by pathspec, never `git push` or open a PR (the owner reviews and pushes).
- **Copy the gitignored env files into the worktree first**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — the pre-commit hook runs `scripts/db-migrate.py --env INT` and the tests need `env/TEST.env`.
- **Migration numbering:** `sql/_migrations/GeneraliDB/` is at `0004` (phase 1 took `0003` and `0004`). Run `python scripts/db-migrate.py --dry-run` before claiming a number — peers number migrations too. Migrations are immutable once applied; to undo one, add another.
- **After every schema migration** run `python sql/sync-from-db.py` and stage the regenerated files under `sql/GeneraliDB/` in the same commit, or the `sql-sync-check` hook blocks the commit. Never hand-edit files under `sql/GeneraliDB/` — they are generated from INT.
- **Two writers, both in this repo:** `nx_lib/views/generali.py` (reads + the effort-table CRUD) and `scripts/generali-import/{local,remote}/csvToSql.ps1` (the daily CSV MERGE into `reportjob`). **The two importer copies are near-identical and must be changed together** — `local/` and `remote/` differ only in how they reach the server.
- **A third consumer exists in the app — and it is seven rows, not one:** `dbo.ReportingSources` registers `generali_pdqm`, `generali_attendance`, `generali_baseservices`, `generali_projects`, `generali_iss`, `generali_documents` and `generali_imports` (migrations `0011`, `0117`, `0119`). Each row stores a `BaseObject` **and** a `ColumnsJSON` full of field names, so any table *or column* rename needs an accompanying `NexoraDB` migration. `dbo.ReportingMetrics.BaseField`/`FilterJson` store field names too (`EffortInHours`, `CASE_ID`, `DOC_NK1`, `DOC_NK2`).
- **The app reads a view, not the table.** `nx_lib/views/generali/documents.py` hits `[dbo].[v_ReportJobJoinDefinitions]` in 12 places and never touches `ReportJob` directly. That view is the seam that makes phase 3 cheap — and it carries its own `WHERE ifl.Value = 'CaptivaCapture'`, which hides two thirds of the table from the app.
- **Deploy ordering is the real risk.** `deploy.yml` applies pending migrations to PROD **before** stopping the app pool. For the seconds between, PROD runs the *old* code against the *new* schema. Every rename migration must therefore leave a compat view/synonym behind under the old name.
- **Tests:** `tests/integration/test_generali_pdqm_routes.py` covers the PDQM route. The TEST database (`sql/test/schema.sql`) has **no** Generali tables — Generali integration tests skip when the engine is unset; keep that degradation working.
- **`ENVIRONMENT=INT` points at a full copy of the customer's data** (2.47M rows, scan dates 2025-11-03 → 2026-08-24). Profile there, never on PROD.

## What is actually in there (measured 2026-08-27)

**25 tables + 1 view.** Row counts:

| Table | Rows | Cols | What it is |
|---|---:|---:|---|
| `ReportJob` | 2,468,923 | 79 | one row per document — the whole dataset |
| `CategoryTranslation` | 162 | 5 | de/fr/it labels for `AdditionalServices` values only |
| `DokumentenTyp` | 159 | 2 | lookup |
| `CSVImportLog` | 87 | 10 | one row per import run |
| `AdditionalServices` | 32 | 3 | category catalogue for the effort tables |
| `PDQMMapping` | 27 | 4 | category catalogue for PDQM |
| `Empfaenger` 19 · `Ursprung` 12 · `InterfaceLink` 9 · `Kommunikation` 7 · `Waehrung` 6 · `Sprache` 5 · `DokumentenStatus` 5 · `ScanOrt` 3 · `Nachkontrolle` 3 · `NotifikationsStatus` 3 · `Eingangskanal` 2 · `Richtung` 2 | 2–19 | 2 | 12 more `(ID, Value)` lookups |
| `Attendance` 10 · `ReportingISS` 6 · `PDQMReport` 5 · `ProjectManagement` 3 · `BaseServices` 2 | 2–10 | 6–8 | the effort-logging cluster |
| `v_ReportJobJoinDefinitions` | view | 77 | `ReportJob` + the lookups resolved to text |

**The concrete problems, with evidence:**

1. **Two languages, three casing styles.** Tables: `DokumentenStatus`, `Empfaenger`, `Waehrung`, `ScanOrt` … next to `AdditionalServices`, `ProjectManagement`, `CSVImportLog`. Columns: `DOC_SCHADEN_NR` (SCREAMING_SNAKE, German, `DOC_` prefix) next to `DOC_DateCreated` (same prefix, PascalCase) next to `InsertedAt` next to `ReportingISS.category` (lowercase).
2. **Nothing is typed.** Every text column is `varchar(100)` no matter what it holds; the widest value in the whole table is 64 characters. Money, counts, dates and booleans are all strings:
   - `DOC_BETRAG` — 12,491 non-null, **12,284 of them do not convert to `decimal`** (Swiss thousands separators / currency suffixes). A number that has never been a number.
   - `DOC_PENDING` — `'True'` ×512,840, `'False'` ×1,230,285, `NULL` ×725,798. A `bit`.
   - `DOC_BELEGDATUM` — 603 non-null, 401 unconvertible to `date` (`dd.MM.yyyy`).
   - `DOC_ANZAHL` — 2,291 non-null, 261 unconvertible to `int`.
3. **Dead columns.** `DOC_JOURNAL_ID`, `DOC_DOKUMENT_ID`, `DOC_DOKUMENT_URL`, `DOC_BARCODENR`, `DOC_PageSize`: **0 non-null rows out of 2.47M**. `DOC_ALFpages` / `DOC_ALFdpages`: 3,443 non-null, `MAX(LEN(...)) = 0` — empty strings.
4. **A dead SAP block.** 11 `DOC_SAP*` columns: 6 are entirely empty, the other 5 are filled on 3,443 rows (**0.1%**). 11 columns × 2.47M rows of `NULL` in the middle of the hot table.
5. **The MERGE key is unindexed.** `DOC_ID` is unique across all 2,468,923 rows and is what the importer `MERGE`s on — with no unique constraint and no index on it. Same for `DOC_SCANDATUM`, which every report filters by. `ReportJob` has exactly **one** index: the clustered PK on the surrogate `RecordID`.
6. **Constraint names are compiler garbage.** `PK__Dokument__3214EC271A02B9B9`, `PK__Reportin__3214EC2712ABEB25` — auto-named, so they differ between INT and PROD and churn `sql/GeneraliDB/` on every re-dump. Foreign keys are named after the *column* (`FK_DOC_NK1`), not the relationship.
7. **Four tables doing one job.** `Attendance`, `BaseServices`, `ProjectManagement`, `PDQMReport` are all `(EffortInHours|Quantity, UserID, ForDate, Category…, RecordDateTime)` with 2–10 rows each, and each one has its own ~200-line CRUD block in `generali.py` (11 SQL references apiece).
8. ~~**The reporting source points at the wrong table.**~~ **Withdrawn 2026-09-10.** `generali_pdqm` → `dbo.PDQMReport` is correct, and a second source `generali_documents` → `dbo.v_ReportJobJoinDefinitions` covers the big table (NexoraDB migration `0119`, added after this plan was written). See Q1.

## Decisions locked in

| # | Decision | Rationale |
|---|---|---|
| D1 | **English, PascalCase, plural for tables**; PascalCase for columns; no `DOC_` prefix; no abbreviations except the ones the customer uses in the business (`Iss`, `Sap`, `Gav`, `Gpv`, `Rgi`, `Syrius`). | One rule, mechanically checkable. Matches `NexoraDB` (`ProcessSources`, `FieldLabels`, `ReportingSources`). |
| D2 | Primary key column is `Id`; a foreign key column is `<ReferencedEntitySingular>Id` (`DocumentTypeId`); a role-qualified one keeps the role (`PostCheck1Id`). | Removes the guessing game `DOC_NK1` currently is. |
| D3 | Constraints are named explicitly: `PK_<Table>`, `FK_<Table>_<Referenced>[_<Role>]`, `UQ_<Table>_<Cols>`, `IX_<Table>_<Cols>`. | Auto-named PKs differ per environment and churn the generated DDL dumps. |
| D4 | **Keep the 13 lookups as separate typed tables** (renamed), do not merge them into one polymorphic `CodeLists`. | A single lookup table cannot express "this column may only reference rows of kind X" without composite-key tricks; the FK graph is what makes the diagram and the joins readable. The cost is 13 tiny tables, which is not a cost. |
| D5 | `ReportJob` → **`Documents`**, and it **stays one wide denormalized table**. | It is a reporting landing table with a 1:1 row-to-document mapping (`DOC_ID` unique on all 2.47M rows). Normalizing it would buy nothing and break every report. |
| D6 | The `DOC_SAP*` block **does** move out, to `DocumentSapMetadata` (1:1, `DocumentId` FK), keeping only the 5 columns that are ever populated. | 0.1% fill. Six of them are provably always `NULL`. |
| D7 | Type fixes never destroy the original string. Each retyped column lands as a **new typed column beside the old one**, backfilled with a documented cleaning rule, and the old column is dropped a release later. | 12,284 of 12,491 `DOC_BETRAG` values do not parse. A blind `ALTER COLUMN` would silently zero the only money in the database. |
| D8 | Every rename ships with a **compat view under the old name** in the same migration; the view is dropped one release later. | `deploy.yml` migrates PROD *before* stopping the app pool — old code meets new schema on every deploy. |
| D9 | The effort cluster is **renamed in phase 2 and merged in phase 5**, not both at once. | The merge is an app refactor (~800 lines of `generali.py`), the rename is not. Shipping them together would make one revert impossible without the other. |
| D10 | `CategoryTranslation` folds into per-locale columns on the catalogue tables (`NameDe`/`NameFr`/`NameIt`), mirroring `NexoraDB.dbo.FieldLabels`. | 162 rows, one consumer, and the house already has this pattern. Kills a join and a `WHERE Locale = ?`. |

## Naming rulebook (the thing to agree on before any SQL)

```
Tables       PascalCase, English, plural            Documents, DocumentTypes, ImportRuns
Views        v + table name                          v_Documents
Columns      PascalCase, English, no prefix          ScannedAt, PolicyNo, RecipientId
Keys         Id                                      Documents.Id
Foreign keys <EntitySingular>Id                      DocumentTypeId, CurrencyId
Booleans     Is/Has prefix, bit NOT NULL             IsPending
Dates        <Verb>At for datetime2, <Noun>Date      ScannedAt, ImportedAt, VoucherDate
Numbers      No unit in the name unless ambiguous    EffortHours, Amount, Quantity
Text keys    …No for business numbers                PolicyNo, ClaimNo, ContractNo
Constraints  PK_/FK_/UQ_/IX_ + table + columns       IX_Documents_ScannedAt
```

### Table rename map

| Today | Becomes |
|---|---|
| `ReportJob` | `Documents` |
| `DokumentenStatus` | `DocumentStatuses` |
| `DokumentenTyp` | `DocumentTypes` |
| `Eingangskanal` | `InboundChannels` |
| `Empfaenger` | `Recipients` |
| `InterfaceLink` | `InterfaceLinks` |
| `Kommunikation` | `CommunicationTypes` |
| `Nachkontrolle` | `PostChecks` |
| `NotifikationsStatus` | `NotificationStatuses` |
| `Richtung` | `Directions` |
| `ScanOrt` | `ScanLocations` |
| `Sprache` | `Languages` |
| `Ursprung` | `Origins` |
| `Waehrung` | `Currencies` |
| `CSVImportLog` | `ImportRuns` |
| `CategoryTranslation` | *(folded into the catalogue tables, D10)* |
| `AdditionalServices` | `EffortCategories` |
| `PDQMMapping` | `QualityCheckCategories` |
| `PDQMReport` | `QualityCheckEntries` |
| `Attendance` | `AttendanceEntries` |
| `BaseServices` | `BaseServiceEntries` |
| `ProjectManagement` | `ProjectEntries` |
| `ReportingISS` | `IssReports` |
| `v_ReportJobJoinDefinitions` | `v_Documents` |

Lookup columns everywhere: `ID` → `Id`, `Value` → `Name` (+ `NameDe`/`NameFr`/`NameIt` in phase 5).

### `ReportJob` → `Documents` column map

`RecordID`→`Id` · `CASE_ID`→`ScanCaseId` **(Q2)** · `CASE_FOLDERNAME`→`ScanCaseFolderName` · `DOC_ID`→`DocumentId` · `DOC_COUVERT_ID`→`EnvelopeId` · `DOC_CASE_ID`→`CaseId` **(Q2)** · `DOC_JOURNAL_ID`→*drop* · `DOC_DateCreated`→`CreatedAt` · `DOC_COUVERTDOCCOUNT`→`EnvelopeDocumentCount` · `DOC_KOMMUNIKATION`→`CommunicationTypeId` · `DOC_INITIAL_USER`→`InitialUser` · `DOC_SCANDATUM_INITIAL`→`InitialScannedAt` · `DOC_SCANDATUM`→`ScannedAt` · `DOC_DOKUMENTENTYP`→`DocumentTypeId` · `DOC_EMPFAENGER`→`RecipientId` · `DOC_EMPFAENGERADRESSE`→`RecipientAddress` · `DOC_SPRACHE`→`LanguageId` · `DOC_NOTIFIKATIONSSTATUS`→`NotificationStatusId` · `DOC_VERTRAULICHKEIT`→`ConfidentialityCode` · `DOC_RICHTUNG`→`DirectionId` · `DOC_DOKUMENT_ID`→*drop* · `DOC_DOKUMENTENORDER`→`DocumentOrder` · `DOC_DOKUMENTENSTATUS`→`DocumentStatusId` · `DOC_DOKUMENT_URL`→*drop* · `DOC_EINGANGSKANAL`→`InboundChannelId` · `DOC_ANTRAG_NR`→`ApplicationNo` · `DOC_ANTRAG_NR_MULTI`→`ApplicationNos` · `DOC_PARTNER_NR_SYRIUS`→`PartnerNoSyrius` · `DOC_PARTNER_NR_GAV`→`PartnerNoGav` · `DOC_PARTNER_NR_GPV`→`PartnerNoGpv` · `DOC_PARTNER_NR_RGI`→`PartnerNoRgi` · `DOC_PRODUKT_CODE`→`ProductCode` · `DOC_BEMERKUNG`→`Remark` · `DOC_SCANORT`→`ScanLocationId` · `DOC_SCANUSER`→`ScanUser` · `DOC_FORMULAR_NR`→`FormNo` · `DOC_PERSONAL_NR`→`PersonnelNo` · `DOC_POLICEN_NR`→`PolicyNo` · `DOC_POLICEN_NR_MULTI`→`PolicyNos` · `DOC_SCHADEN_NR`→`ClaimNo` · `DOC_VERFAHREN_NR`→`ProceedingNo` · `DOC_WAEHRUNG`→`CurrencyId` · `DOC_BETRAG`→`Amount` *(retyped, D7)* · `DOC_BUCHUNGSKREIS_NR`→`CompanyCode` · `DOC_ANZAHL`→`Quantity` *(retyped)* · `DOC_GESCHAEFTSART`→`BusinessType` · `DOC_KONTAKTPERSON`→`ContactPerson` · `DOC_KREDITOREN_NR`→`VendorNo` · `DOC_OFFERTEN_NR`→`QuoteNo` · `DOC_KONTONUMMER`→`AccountNo` · `DOC_BEZEICHNUNG`→`Description` · `DOC_PENDING`→`IsPending` *(retyped bit)* · `DOC_ALFdpages`/`DOC_ALFpages`/`DOC_PageSize`→*drop* · `DOC_SAP*`→`DocumentSapMetadata` *(D6)* · `DOC_BARCODENR`→*drop* · `DOC_BELEGDATUM`→`VoucherDate` *(retyped date)* · `DOC_FONDSNAME`→`FundName` · `DOC_VERTRAGSNUMMER`→`ContractNo` · `DOC_VERTRAGSPARTNER`→`ContractPartner` · `DOC_DOSSIER_NR`→`DossierNo` · `DOC_REFERENZNUMMER`→`ReferenceNo` · `DOC_ORIGIN`→`OriginId` · `DOC_INTERFACE_LINK`→`InterfaceLinkId` · `DOC_NK1`→`PostCheck1Id` · `DOC_NK2`→`PostCheck2Id` · `InsertedAt`→`ImportedAt` · `SourceCSVFileName`→`SourceCsvFileName` + new `ImportRunId` FK **(phase 4)**

---

## Phase 1 — Keys, indexes and constraint names (no renames, ships alone) — **DONE 2026-09-10**

*Pure win, zero blast radius: nothing is renamed, so no code changes at all.*

- [x] **1.1** Migration `sql/_migrations/GeneraliDB/0003_reportjob_keys_and_indexes.sql`:
  - [x] `UQ_ReportJob_DOC_ID` — unique index on `DOC_ID`, **filtered `WHERE DOC_ID IS NOT NULL`** (re-verified 2026-09-10: 2,682,707 distinct / 2,682,707 rows, 0 nulls). The filter is not cosmetic: `csvToSql.ps1` deliberately lets rows with a NULL `DOC_ID` through (`WHERE rn = 1 OR [DOC_ID] IS NULL`), so an unfiltered `UNIQUE` index would break the import the first night two such rows arrive. Verified on INT that the optimiser still matches the filtered index for the MERGE's join predicate (plan goes Hash Match + full scan → Nested Loops + Index Seek).
  - [x] `IX_ReportJob_DOC_SCANDATUM` — key `DOC_SCANDATUM`, `INCLUDE (DOC_INTERFACE_LINK, DOC_KOMMUNIKATION, DOC_DOKUMENTENTYP, DOC_EMPFAENGER, DOC_SPRACHE, DOC_EINGANGSKANAL, DOC_NK1, DOC_NK2)`. `DOC_INTERFACE_LINK` is in the list because the view itself filters on it (see the finding below).
  - [x] `IX_ReportJob_DOC_DOKUMENTENTYP_SCANDATUM` / `..._DOKUMENTENSTATUS_...` — **rejected, measured.** The covering index above already serves both group-by queries (`doctype_30d` 279 → 58 ms), and `DOC_DOKUMENTENSTATUS` is referenced nowhere in `nx_lib/views/generali/`.
- [x] **1.2** Migration `0004_name_the_constraints.sql`: 22 auto-named PKs → `PK_<Table>`, 14 `FK_DOC_*` → `FK_ReportJob_<Referenced>[_<Role>]`, and 5 auto-named **default** constraints → `DF_<Table>_<Column>` (they churn the dumps for the same reason the PKs do). Driven off the system catalogs and matched by *table and column*, never by the current name — the auto-generated names differ between INT and PROD, so a migration that hardcoded them would apply on INT and fail on PROD.
- [x] **1.3** Measured on the live INT copy instead of a real import run (the importer needs the mail attachment): a 500-row `MERGE` batch reproduced exactly, in a rolled-back transaction. **3,169 ms → 2,435 ms (−23%)**; a daily CSV is 16k–25k rows = 32–50 batches, so ~25–35 s off a ~320 s run. Dashboard, warm cache: KPI 250 → 25 ms, trend 303 → 46 ms, latest-day probe 310 → 68 ms, doctype 279 → 58 ms, filter-options `DISTINCT` 342 → 149 ms, document detail 290 → 7 ms. Index build 9 s each; sizes 136 MB + 133 MB against a 1,366 MB table.
- [x] **1.4** `python sql/sync-from-db.py`, `sql/GeneraliDB/` re-dumped and staged.

**Three findings from phase 1 that change later phases:**

1. **`v_ReportJobJoinDefinitions` has a hidden `WHERE ifl.Value = 'CaptivaCapture'`.** The app therefore sees **890,298 of 2,682,707 rows** (33%). 1,093,412 rows have a NULL `DOC_INTERFACE_LINK` and are invisible to every `/generali/*` page. Phase 3 must carry this predicate into `v_Documents` deliberately, not by accident — and someone should confirm it is still the intent.
2. **Every `CSVImportLog` run to date reports `RowsUpdated = 0`.** The daily MERGE is pure insert; the UPDATE branch has never fired. That is what makes the `DOC_ID` seek worth having, and it also means phase 4's retyping never has to cope with a row changing type mid-life.
3. **The remaining 2.4 s per import batch is not the database.** It is the 500-row `VALUES` literal `csvToSql.ps1` builds and SQL Server re-parses per batch. A table-valued parameter or `bcp` would take far more off the nightly run than any further index. Out of scope for this plan — worth its own issue.

## Phase 2 — Lookups and the effort cluster get English names — **DONE 2026-09-10**

- [x] **2.1** Migration `0005_english_table_names.sql`: `sp_rename` the 13 lookup tables and their `ID`/`Value` columns per the map. **No compat views for the lookups** — nothing names them directly (their only consumer is `v_ReportJobJoinDefinitions`, rebuilt on the new names in the same migration; verified by grep across `nx_lib/`, `templates/`, `static/`, `scripts/`, `tests/` and by 31 days of INT Query Store). Thirteen views nothing reads would only be thirteen more things for phase 6 to drop. D8 still applies to every table the app *does* name.
- [x] **2.2** Same migration: the effort tables renamed as mapped, plus `CategoryTranslation`→`CategoryTranslations`. Column renames limited to the two genuine outliers — `IssReports.category`→`Category` and `ImportRuns.Min/MaxScanDatum`→`Min/MaxScannedAt`. The effort tables' other columns (`EffortInHours`, `UserID`, `RecordDateTime`) are deliberately left alone: phase 5 merges those four tables into one `EffortEntries` and can name their columns then. **`CategoryTranslations.SourceTable` stores table names as data** and had to be updated with them (162 rows).
- [x] **2.2b** Migration `0006_qualitycheckcategories_primary_key.sql`: `QualityCheckCategories` (was `PDQMMapping`) turned out to be the only table in the database with **no primary key at all** — found while verifying 0005 (24 tables, 23 PKs). Added.
- [x] **2.3** `nx_lib/views/generali/` (a package now, not one module): 13 `[Generali].[dbo].[…]` references swapped across `attendance.py`, `baseservices.py`, `projectmanagement.py`, `pdqm.py`, `importstatus.py`, `reporting.py`, plus the two `WHERE SourceTable = …` literals and `reporting.py`'s `category`/`ontime` SQL identifiers. `_crud.py` needed no change beyond its docstring — it takes the table name from each page's `CrudTable` descriptor.
- [x] **2.4** `NexoraDB` migration `0128_generali_renamed_objects.sql`. **There are seven Generali reporting sources, not two** — `generali_pdqm`, `generali_attendance`, `generali_baseservices`, `generali_projects`, `generali_iss`, `generali_documents`, `generali_imports` (migrations `0011`, `0117`, `0119`). Six `BaseObject` values repointed; `generali_documents` waits for phase 3. `ColumnsJSON` also stores field names, so the `category` and `Min/MaxScanDatum` tokens were patched there too. `ReportingAiAudit`/`ReportingSqlAudit` deliberately untouched — they are a record of what ran, not a live reference.
- [x] **2.5** `scripts/generali-import/{local,remote}/csvToSql.ps1`: both copies. `scripts/generali-import/.env.example` still has a stale `CSVImportLog` mention in a comment — the tooling here refuses to read `.env*` files, so that one line needs a human.
- [x] **2.6** `pytest -k generali`: 56 passed. Verified against the **real INT database**, not mocks: all 7 pages 200, all 11 `/api/generali/*` endpoints returned real rows with `success: true`, the French locale round-trip proved the renamed `CategoryTranslations` + rewritten `SourceTable` data (36 and 18 translations), and a report run against **every one of the 7 reporting sources** came back with data (`FROM [dbo].[QualityCheckEntries]`, `MinScannedAt`/`MaxScannedAt` populated). Screenshots in `var/screenshots/220-phase2-*.png`.

## Phase 3 — `ReportJob` → `Documents` — **DONE 2026-09-10**

- [x] **3.1** Migration `0007_reportjob_to_documents.sql`: table renamed, **61 of 79** columns renamed off a map that is checked against `sys.columns` at generation time, so a column added since this plan was written cannot slip through unrenamed. The other 18 keep their names on purpose — the five provably-dead ones, the two empty-string ones and the whole `DOC_SAP*` block are dropped or moved by phase 4, and renaming a column on its way to the bin is work done twice.
  - **Trap:** `sp_rename` on `DOC_ID` fails with Msg 5074/4922 because `UQ_ReportJob_DOC_ID` is a **filtered** index and its predicate is a real dependency. Every other index tracks columns by id and follows a rename by itself. The migration drops that index first and recreates it as `UQ_Documents_DocumentId` (~9 s).
  - **Trap:** a case-only rename (`SourceCSVFileName` → `SourceCsvFileName`) is skipped by a `COL_LENGTH(new) IS NULL` guard, because `COL_LENGTH` is case-insensitive. Migration `0008` redoes it with a case-sensitive `sys.columns` check.
  - `DOC_BETRAG`/`DOC_ANZAHL`/`DOC_PENDING`/`DOC_BELEGDATUM` became `AmountText`/`QuantityText`/`PendingText`/`VoucherDateText`, not `Amount`/`Quantity`/`IsPending`/`VoucherDate` — those names are reserved for the typed columns phase 4 adds *beside* them (D7).
- [x] **3.2** `CREATE VIEW dbo.ReportJob` under the old column names, updatable, so the importer keeps working through the deploy window.
- [x] **3.3** `v_Documents` added — lookups resolved, English output names. `v_ReportJobJoinDefinitions` is now a compat view over it, still exposing the old output names.
- [x] **3.4** `nx_lib/views/generali/documents.py` moved to `v_Documents`: 83 tokens, including **both** allowlists (`allowed_sort_cols`, `allowed_group_cols`) and the `SELECT DISTINCT {col}` filter builder. The JSON keys the front end reads (`doc_id`, `doc_scandatum`, …) are deliberately **unchanged** — the HTTP contract is not part of this issue — but `templates/generali_documents.html` (11 tokens) and `templates/js/_generali_documents_js.html` (67 tokens) had to move with the SQL because they send the sort/group column names and hardcode the detail-panel field list. A visible win: the detail panel now reads `ClaimNo` / `PolicyNo` / `ScannedAt` instead of `SCHADEN_NR` / `POLICEN_NR` / `SCANDATUM`.
- [x] **3.5** Importer: both copies. 77 `$cols` entries, 59 renamed, plus `MERGE INTO Documents` and the four `[DOC_ID]` references. **Careful:** the same file reads `$row.DOC_ID` from the *CSV header*, which must not change — the rename is scripted against the table map and touches only the SQL. Verified by parsing `$cols` back out of both `.ps1` files, building the real MERGE and running it against INT in a rolled-back transaction: 77/77 columns resolve, 500 rows inserted, 0 leaked.
- [x] **3.6** NexoraDB `0129_generali_documents_renamed_fields.sql`: `generali_documents` repointed to `dbo.v_Documents`, its 19 `ColumnsJSON` fields rewritten, `ReportingMetrics.BaseField` `CASE_ID` → `ScanCaseId` and the `DOC_NK1`/`DOC_NK2` `FilterJson` → `PostCheck1`/`PostCheck2`, and saved `Reports.DefinitionJSON` rewritten for any report built on this source (INT has none; PROD has had the source since `0119` and might).
- [x] **3.7** Re-dumped and verified against the real INT database: `pytest tests/unit` 1763 passed, `-k generali` 56 passed, `-k reporting` 891 passed; all `/api/generali/*` endpoints green including sort/group/search variants and the by-id detail route (now returning English keys); a three-measure report run on `generali_documents` returns data; the dashboard renders 234,978 documents with every chart populated. Screenshots: `var/screenshots/220-phase3-*.png`.
  - One test needed updating, correctly: `tests/integration/test_generali_stats_coverage.py`'s fake cursor dispatches on SQL text and matched `GROUP BY CAST(DOC_SCANDATUM AS DATE)`.
  - **Pre-existing, not caused by this phase:** `/generali-dashboard` fires `/api/generali/stats` before both date inputs are set and takes two 400s ("startDate and endDate are required"). The guard is unchanged in `git show HEAD`. Worth its own issue.

## Phase 4 — Real types, dead weight gone — **DONE 2026-09-10** (4.4/4.5 deliberately skipped)

- [x] **4.1** Migration `0010_documents_typed_columns.sql`. **Computed columns, not backfilled ones** — a backfilled column is right on the day it ships and wrong from the next import unless `csvToSql.ps1` is taught to write it too; one expression cannot drift. Not `PERSISTED`: nothing to add (no size-of-data ALTER, no lock, no storage) and these are read over at most 13k non-null rows. The expressions are deterministic and precise, so `PERSISTED` is a one-line upgrade if a report ever needs an index.
  - **`Quantity` is `decimal(18,3)`, not `int` — the plan's rule would have corrupted data.** The 302 values it called unconvertible are `0.102`, `0.469`, `0.987`: real fractional quantities. Worse, the column holds **2,297 empty strings**, and `TRY_CONVERT(int, '')` returns **0**, not NULL — so `int` would have written 2,297 fabricated zeros into a quantity column. With `NULLIF(...,'')` and decimal: 304 real values, 304 converted, **residual 0**.
  - **`Amount`: the column is not money.** Of 9,531 non-blank values, 9,183 are the literal `'CH04'` and the rest `'CH00'`, `'CH70'`, `'LI00'`, `'CH96'` — IBAN country-and-checksum prefixes. **207** are numbers (max 13224.00, sum 49443.35). No cleaning rule can fix that; the source system is writing the wrong field. The owner chose to add the column anyway, so it exists and is 97.8% NULL. **Raise `DOC_BETRAG` with Generali.**
  - **`VoucherDate`:** 694 non-null, all `dd.MM.yyyy HH:mm`, style 104 parses every one — **residual 0**. The plan's fear of 401 failures does not reproduce. The explicit style is also what makes the expression deterministic.
  - **`IsPending`:** 579,532 `True`, 1,321,167 `False`, 782,008 NULL, **zero** other values. NULLs stay NULL — unknown is not false.
- [x] **4.2 / 4.3 (reordered: move first, drop second).** `0011_document_sap_metadata.sql` creates `dbo.DocumentSapMetadata` and copies the 3,719 SAP-bearing rows, with a row-count guard that refuses to proceed on a mismatch; `0012_documents_drop_dead_columns.sql` then drops 17 columns and rebuilds all three views. Nothing is destroyed until the copy has been checked.
  - Re-profiled immediately before writing 0012, and the plan's numbers had moved: the SAP split is **6 populated / 5 empty**, not 5/6, and **`DOC_DOKUMENT_ID` is no longer provably empty** — one row written 2026-09-02 holds free text ("Keine aktive Policen-Nr. bekannt…"), somebody's remark in the wrong column. It is **not** dropped. One row is still data.
  - The side table's FK is `DocumentRecordId` → `Documents.Id`, not `DocumentId` as D2 would give: `Documents` already has a `DocumentId` holding the external GUID, and that column's unique index is *filtered*, which SQL Server will not accept as an FK target anyway.
  - **SAP data is live** — 157 rows scanned in September, last imported 2026-09-09 — so the importer had to learn to write the side table. Dropping the columns without that would have been silent, ongoing data loss. Both `csvToSql.ps1` copies now run a second MERGE into `DocumentSapMetadata` after the main one, with the same `rn = 1` dedupe.
- [ ] ~~**4.4** right-size `varchar(100)` → measured width~~ — **skipped, deliberately.** Narrowing a column is a size-of-data operation; doing it across ~40 columns of a 2.68M-row table is a long, log-heavy write for an optimizer-estimate gain nobody has asked for. The measurement is banked for whoever wants it: 34 columns declared 100+ hold ≤ 20 characters, and the widest value in the whole table is `Description` at 148.
- [ ] ~~**4.5** add `ImportRunId` FK~~ — **skipped.** It is an addition, not a type fix, and it wants its own issue: the backfill from `SourceCsvFileName` is ambiguous (the same file name recurs across runs).
- [x] **4.6** No `generali.py` change was needed — the typed columns are additive and the page reads the view. `templates/js/_generali_documents_js.html` lost the whole "SAP / ALF" detail group (every field in it was dropped) and gained `Amount`, `Quantity`, `VoucherDate` and `IsPending` beside their text originals. The now-unused `SAP / ALF` msgid was removed from the catalogs via the full extract → update → compile cycle.
- [x] **4.7** Verified against the real INT database: 207 amounts / 304 quantities / 694 voucher dates / the exact 579,532-1,321,167-782,008 pending split come back through `v_Documents`; the by-id detail route returns `Amount` as `353.95` next to `AmountText` `'353,95'` and **none** of the 17 dropped keys; both importer copies parse clean under the PowerShell parser and both MERGEs (60-column main + the new SAP one) run against INT in a rolled-back transaction with 0 leaked rows and the side table still at 3,719; `pytest tests/unit` and the translation suite pass. Screenshot: `var/screenshots/220-phase4-documents-detail.png` (note `IsPending: False` beside `PendingText: False`).

## Phase 5 — Better logic (optional, own release)

- [ ] **5.1** Fold `CategoryTranslation` into `EffortCategories`/`QualityCheckCategories` as `NameDe`/`NameFr`/`NameIt` (D10); drop the table and the `WHERE SourceTable = … AND Locale = ?` join in `generali.py` (~line 1163).
- [ ] **5.2** Merge `AttendanceEntries` + `BaseServiceEntries` + `ProjectEntries` + `QualityCheckEntries` into `EffortEntries(Id, EntryType, UserId, ForDate, EffortHours NULL, Quantity NULL, CategoryId, Comment, RecordedAt)` (D9) — 20 rows total move. Collapse the four ~200-line CRUD blocks in `generali.py` into one parametrised by `EntryType`; keep the four routes and four pages.
- [ ] **5.3** Add per-locale names to the 13 lookups so the UI stops needing `CategoryTranslation`-style side lookups at all.

## Phase 6 — Take the scaffolding down

- [ ] **6.1** One release after phases 2-4 ship to PROD: drop every compat view created in phases 2-3. Q3 is answered (no external consumer), so the gate is no longer "who else reads this" but two concrete facts:
  1. **The importer on prdimpexp01 must be running the new `csvToSql.ps1` first.** It is copied there by hand, not by `deploy.yml`, and the compat views `dbo.ReportJob` / `dbo.CSVImportLog` are what keep an un-updated copy alive.
  2. `dbo.v_ReportJobJoinDefinitions` has no in-repo consumer left after phase 3 (the app and the `generali_documents` reporting source both read `v_Documents`), so it can go with the rest.
  The phase-4 legacy text columns (`AmountText`, `QuantityText`, `PendingText`, `VoucherDateText`) **stay**: the typed columns are computed *over* them, and keeping the original string is what D7 wanted anyway.
- [ ] **6.2** Rename `v_ReportJobJoinDefinitions` out of existence once nothing references it.
- [ ] **6.3** Final `sql/sync-from-db.py`; add a short "Generali tenant DB" section to `docs/design/` describing the schema and the naming rulebook so the next person inherits the rule, not the exception.

---

## Open questions for the owner

- **Q1 — ~~Is `generali_pdqm` pointed at the right table?~~ ANSWERED 2026-09-10: yes, and the premise is stale.** `dbo.ReportingSources` now holds **two** Generali rows — `generali_pdqm` → `dbo.PDQMReport` (correct; PDQM really is its own 5-row effort log) and `generali_documents` → `dbo.v_ReportJobJoinDefinitions`, added by NexoraDB migration `0119_generali_documents_source_and_labels.sql` after this plan was written. Nothing is mis-registered. Phase 2/3 must update **both** `BaseObject` values when the tables are renamed, not one.
- **Q2 — `CASE_ID` vs `DOC_CASE_ID`. ANSWERED 2026-09-10: proceed with `ScanCaseId` / `CaseId`, provided nothing breaks** (so: compat view, as for every other rename). Re-measured, and the plan's original figures were wrong because they counted empty strings as values. `CASE_ID` is non-blank on **29,760 rows (1.1%)**, always a GUID, always paired with a non-blank `CASE_FOLDERNAME`, groups 2–25 documents, and occurs only on `EARLY SCANNING` — a scan batch/folder id. `DOC_CASE_ID` is non-blank on **1,741 rows (0.06%)**, not 35.5%, and looks like `CID001126050` — a business case reference. Never both.
- **Q3 — external consumers. ANSWERED 2026-09-10: none.** Phase 6 is unblocked. (INT Query Store over 31 days independently showed only the importer, the nexora pages, the nexora reporting sources and this work's own profiling.) Phase 6 still cannot ship in the *same release* as phases 2–3 — the compat views exist for the deploy window, not for external readers.
- **Q4 — German terms as extended properties. ANSWERED 2026-09-10: no.** All English, no `sp_addextendedproperty`.

## Risks

| Risk | Mitigation |
|---|---|
| PROD runs old code against new schema for seconds on every deploy (`deploy.yml` migrates before stopping the pool) | D8 — compat views in the same migration; drop them a release later |
| The daily CSV import breaks at 03:00 and nobody notices until the reports are empty | Ship rename phases right after an import completes; check `ImportRuns` the next morning; the importer already records `Status` |
| `Amount` conversion silently drops the 12,284 unparseable values | D7 — new column beside the old, residual count recorded in the migration, old column kept a full release |
| An external consumer breaks (Q3) | Phase 6 gated on Q3; everything before it keeps the old names alive |
| A rename migration is applied to INT by the pre-commit hook while a peer session is mid-test | Normal here — announce in the handoff, and `db-migrate --dry-run` before numbering |

## Rollback

Phases 1–5 are each a single migration plus its code change: revert the code commit and add a compensating migration (`sp_rename` back — migrations are immutable). The data never moves except in 4.3 and 5.2, both of which copy before dropping, both under 4,000 rows. Nothing in this plan is destructive before phase 6, and phase 6 is gated on Q3.
