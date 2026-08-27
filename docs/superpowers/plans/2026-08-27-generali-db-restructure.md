# Generali DB restructure — English names, one style, better logic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan phase-by-phase. Steps use checkbox (`- [ ]`) syntax. Every table, column, row count and fill rate quoted below was **measured against the live INT `Generali` database on 2026-08-27** (`sys.*` catalogs + a full profiling pass over 2,468,923 `ReportJob` rows) — re-measure before executing, the importer runs daily. Plan file: `docs/superpowers/plans/2026-08-27-generali-db-restructure.md`.

**Issue:** [#220](https://github.com/Sydoc-Code/nexora/issues/220) — the four open questions at the bottom of this plan are repeated there for the owner to answer.

**Goal:** Turn the Generali tenant DB from a half-German, half-English, string-typed CSV landing zone into a schema someone can read: **English names, one naming style, real types, real keys, real indexes** — without a single minute of downtime for `/generali/*` or the daily CSV import.

**Why now:** the reporting source visualizer (`reporting.sources.schema`, shipped 2026-08-27) draws this database, and it draws it honestly: one 79-column table whose columns are `DOC_SCHADEN_NR`-style SCREAMING_SNAKE German, thirteen two-column German lookup tables, four near-identical effort-logging tables, and a `PDQMReport` table with **5 rows** that the reporting registry points at while the 2.47M-row table beside it is what actually holds the data.

**Architecture:** Six phases, each one migration + the code that goes with it, each independently shippable and independently revertible. Renames are `sp_rename` (metadata-only — instant on 2.47M rows, no data copy); every rename ships **with a compatibility view under the old name in the same migration**, because `deploy.yml` applies migrations *before* it stops the app pool, so old code and new schema overlap by seconds on every deploy. The compat views come out one release later.

**Tech stack:** T-SQL migrations in `sql/_migrations/GeneraliDB/` (applied by `scripts/db-migrate.py`, auto-applied to INT by the `sql-migrate-int` pre-commit hook, to PROD by `deploy.yml`), pyodbc via `engine_generali_db`, `nx_lib/views/generali.py` (3,476 lines), and the PowerShell importer under `scripts/generali-import/`.

---

## Context an engineer needs (read first)

- **Branch:** cut from `v3.2.3.1`. Parallel sessions are normal here — work in your own worktree (`git worktree add .claude/worktrees/generali-db -b feat/generali-db-restructure v3.2.3.1`), stage by pathspec, never `git push` or open a PR (the owner reviews and pushes).
- **Copy the gitignored env files into the worktree first**: `Copy-Item C:\dev\nexora\env\*.env <worktree>\env\` — the pre-commit hook runs `scripts/db-migrate.py --env INT` and the tests need `env/TEST.env`.
- **Migration numbering:** `sql/_migrations/GeneraliDB/` is at `0002` today. Run `python scripts/db-migrate.py --dry-run` before claiming a number — peers number migrations too. Migrations are immutable once applied; to undo one, add another.
- **After every schema migration** run `python sql/sync-from-db.py` and stage the regenerated files under `sql/GeneraliDB/` in the same commit, or the `sql-sync-check` hook blocks the commit. Never hand-edit files under `sql/GeneraliDB/` — they are generated from INT.
- **Two writers, both in this repo:** `nx_lib/views/generali.py` (reads + the effort-table CRUD) and `scripts/generali-import/{local,remote}/csvToSql.ps1` (the daily CSV MERGE into `reportjob`). **The two importer copies are near-identical and must be changed together** — `local/` and `remote/` differ only in how they reach the server.
- **A third consumer exists in the app:** the reporting source `generali_pdqm` (`dbo.ReportingSources.BaseObject = 'dbo.PDQMReport'`, migration `0011`). Renaming `PDQMReport` means an accompanying `NexoraDB` migration updating that registry row.
- **The app reads a view, not the table.** `nx_lib/views/generali.py` hits `[dbo].[v_ReportJobJoinDefinitions]` in 11 places and never touches `ReportJob` directly. That view is the seam that makes phase 3 cheap.
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
8. **The reporting source points at the wrong table.** `generali_pdqm` reads `dbo.PDQMReport` — 5 rows, 8 columns — while `ReportJob` next to it has 2.47M. Either the source is mis-registered or PDQM is genuinely the only thing Generali reports on; **this is question Q1 below and it blocks nothing else.**

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

## Phase 1 — Keys, indexes and constraint names (no renames, ships alone)

*Pure win, zero blast radius: nothing is renamed, so no code changes at all.*

- [ ] **1.1** Migration `sql/_migrations/GeneraliDB/0003_reportjob_keys_and_indexes.sql`:
  - [ ] `UQ_ReportJob_DOC_ID` — unique index on `DOC_ID` (verified unique: 2,468,923 distinct / 2,468,923 rows). **This is what the daily `MERGE … ON t.DOC_ID = s.DOC_ID` has been scanning without.**
  - [ ] `IX_ReportJob_DOC_SCANDATUM` — every report filters on it; 10 months of data, ~250k rows/month.
  - [ ] `IX_ReportJob_DOC_DOKUMENTENTYP_SCANDATUM` and `IX_ReportJob_DOC_DOKUMENTENSTATUS_SCANDATUM` — the two lookups the PDQM page groups by. Check the actual plans first; do not add indexes on faith.
- [ ] **1.2** Migration `0004_name_the_constraints.sql`: `sp_rename` every `PK__…` to `PK_<Table>` (24 of them) and every `FK_DOC_*` to `FK_ReportJob_<Referenced>[_<Role>]`.
- [ ] **1.3** Time the daily import before and after on INT (`scripts/generali-import/local/csvToSql.ps1` writes durations into `CSVImportLog`); record the numbers in the commit message.
- [ ] **1.4** `python sql/sync-from-db.py`, stage `sql/GeneraliDB/`, commit.

## Phase 2 — Lookups and the effort cluster get English names

- [ ] **2.1** Migration `0005_rename_lookup_tables.sql`: `sp_rename` the 13 lookup tables and their `ID`/`Value` columns per the map; recreate each old name as a compat view (`CREATE VIEW dbo.Sprache AS SELECT Id AS ID, Name AS Value FROM dbo.Languages`) (D8).
- [ ] **2.2** Same migration: rename the effort tables (`Attendance`→`AttendanceEntries`, `BaseServices`→`BaseServiceEntries`, `ProjectManagement`→`ProjectEntries`, `ReportingISS`→`IssReports`, `AdditionalServices`→`EffortCategories`, `PDQMMapping`→`QualityCheckCategories`, `PDQMReport`→`QualityCheckEntries`, `CSVImportLog`→`ImportRuns`) + compat views. Note `IssReports.category` → `Category` while renaming.
- [ ] **2.3** `nx_lib/views/generali.py`: swap the 44 `[Generali].[dbo].[…]` references to the new names (11 each for `ProjectManagement`, `PDQMReport`, `BaseServices`, `Attendance`, plus `CategoryTranslation` ×2, `CSVImportLog` ×2, `PDQMMapping`, `AdditionalServices`). Mechanical; keep the diff to the names.
- [ ] **2.4** `NexoraDB` migration `0080_point_generali_source_at_renamed_table.sql`: update `dbo.ReportingSources.BaseObject` for `generali_pdqm` (pending **Q1**).
- [ ] **2.5** `scripts/generali-import/{local,remote}/csvToSql.ps1`: `CSVImportLog` → `ImportRuns`, `MinScanDatum`/`MaxScanDatum` → `MinScannedAt`/`MaxScannedAt`. Both copies.
- [ ] **2.6** Run `tests/integration/test_generali_pdqm_routes.py`; browser-verify `/generali/attendance`, `/generali/baseservices`, `/generali/projectmanagement`, `/generali/pdqm`, `/generali/reportingiss`, `/generali/csvimport` against INT (`nx -u -b --loginas:ben.streich`, screenshots to `var/screenshots/`).

## Phase 3 — `ReportJob` → `Documents`

- [ ] **3.1** Migration `0006_rename_reportjob_to_documents.sql`: `sp_rename 'dbo.ReportJob', 'Documents'`, then one `sp_rename` per column from the map (metadata-only, instant).
- [ ] **3.2** Same migration: `CREATE VIEW dbo.ReportJob` selecting the new columns under the old names (D8), and rebuild `v_ReportJobJoinDefinitions` on top of `Documents` so the app keeps working untouched.
- [ ] **3.3** Add `v_Documents` — the resolved view under its new name, lookups joined, English column names. `v_ReportJobJoinDefinitions` becomes a thin `SELECT * FROM v_Documents` alias.
- [ ] **3.4** Move `nx_lib/views/generali.py`'s 11 view references to `v_Documents`, and the `SELECT DISTINCT {col}` filter builder (line ~251) with them — **that one interpolates a column name into SQL, so it carries an allowlist that must be updated in lockstep.**
- [ ] **3.5** Importer: `MERGE INTO reportjob` → `MERGE INTO Documents`, and the 76-entry `$cols` array → the new column names. Both copies. Dry-run against INT with one real CSV before committing.
- [ ] **3.6** Re-dump, verify, commit.

## Phase 4 — Real types, dead weight gone

- [ ] **4.1** Migration `0007_documents_typed_columns.sql`, additive only (D7): add `Amount decimal(18,2) NULL`, `Quantity int NULL`, `VoucherDate date NULL`, `IsPending bit NULL`, `EnvelopeDocumentCount int` (already int), and backfill with documented cleaning rules:
  - `Amount` ← `TRY_CONVERT(decimal(18,2), REPLACE(REPLACE(AmountText, '''', ''), ',', '.'))` — **write the rule against the 12,284 currently-unparseable values first and record the residual count in the migration comment.** If the residue is not ~0, stop and ask; do not ship a money column that silently drops rows.
  - `IsPending` ← `CASE PendingText WHEN 'True' THEN 1 WHEN 'False' THEN 0 END` (725,798 stay `NULL`, which is honest: unknown ≠ false).
  - `VoucherDate` ← `TRY_CONVERT(date, VoucherDateText, 104)` for the `dd.MM.yyyy` residue.
- [ ] **4.2** Migration `0008_documents_drop_dead_columns.sql`: drop `DOC_JOURNAL_ID`, `DOC_DOKUMENT_ID`, `DOC_DOKUMENT_URL`, `DOC_BARCODENR`, `DOC_PageSize` (all provably 0 non-null), `DOC_ALFpages`, `DOC_ALFdpages` (empty strings only), and the 6 never-populated `DOC_SAP*` columns. **Re-run the fill-rate profile immediately before applying** — the importer has run since this plan was written.
- [ ] **4.3** Migration `0009_document_sap_metadata.sql`: create `DocumentSapMetadata(DocumentId FK, SapComponents, SapComponentSize, SapContentType, SapDocumentId, SapDocumentProtection, SapType)`, move the 3,443 populated rows, drop the columns from `Documents` (D6).
- [ ] **4.4** Migration `0010_documents_right_size_text.sql`: `varchar(100)` → `nvarchar(<measured max × 2, rounded up>)` per column; `datetime` → `datetime2(0)`. Widest value in the table today is 64 chars.
- [ ] **4.5** Add `ImportRunId` to `Documents` (FK → `ImportRuns.Id`), backfilled from `SourceCsvFileName`; the importer already knows its `$importLogID` and can write it directly. Keep `SourceCsvFileName` until the next release.
- [ ] **4.6** Importer + `generali.py` updated for the typed columns; the PDQM page's amount formatting can drop its string parsing.

## Phase 5 — Better logic (optional, own release)

- [ ] **5.1** Fold `CategoryTranslation` into `EffortCategories`/`QualityCheckCategories` as `NameDe`/`NameFr`/`NameIt` (D10); drop the table and the `WHERE SourceTable = … AND Locale = ?` join in `generali.py` (~line 1163).
- [ ] **5.2** Merge `AttendanceEntries` + `BaseServiceEntries` + `ProjectEntries` + `QualityCheckEntries` into `EffortEntries(Id, EntryType, UserId, ForDate, EffortHours NULL, Quantity NULL, CategoryId, Comment, RecordedAt)` (D9) — 20 rows total move. Collapse the four ~200-line CRUD blocks in `generali.py` into one parametrised by `EntryType`; keep the four routes and four pages.
- [ ] **5.3** Add per-locale names to the 13 lookups so the UI stops needing `CategoryTranslation`-style side lookups at all.

## Phase 6 — Take the scaffolding down

- [ ] **6.1** One release after phase 3 ships to PROD (and only after confirming no external consumer, **Q3**): drop every compat view created in phases 2–3, plus the phase-4 legacy text columns.
- [ ] **6.2** Rename `v_ReportJobJoinDefinitions` out of existence once nothing references it.
- [ ] **6.3** Final `sql/sync-from-db.py`; add a short "Generali tenant DB" section to `docs/design/` describing the schema and the naming rulebook so the next person inherits the rule, not the exception.

---

## Open questions for the owner

- **Q1 — Is `generali_pdqm` pointed at the right table?** The reporting source reads `dbo.PDQMReport` (5 rows). If Generali reporting is meant to cover the 2.47M-row document table, that registry row should point at `v_Documents` instead, and it is a one-row `UPDATE`, not part of this restructure.
- **Q2 — `CASE_ID` vs `DOC_CASE_ID`.** Both exist, 1.2% and 35.5% filled, never both. Proposed `ScanCaseId` / `CaseId` is a guess; the customer's own term should win.
- **Q3 — Does anything outside this repo read this database?** Power BI, Excel/ODBC, Generali-side tooling, an SSMS query someone runs monthly. Renames are invisible to `SELECT *` but fatal to a saved query. **Phase 6 (dropping the compat views) must not run until this is answered.** Phases 1–5 are safe either way because of D8.
- **Q4 — Should the German business terms survive as documentation?** `Vertraulichkeit`, `Buchungskreis`, `Nachkontrolle` are Generali's own vocabulary. Proposal: extended properties (`sp_addextendedproperty`) carrying the original German name on each renamed column, so the mapping stays discoverable in SSMS without polluting the schema.

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
