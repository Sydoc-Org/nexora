# Generali tenant database

The `Generali` database is the tenant store behind `/generali/*` and the seven
`generali_*` reporting sources. It is reached through `engine_generali_db`
(`nx_lib/db.py`), and read-only through `engine_generali_ro` for the reporting
SQL sandbox.

It has exactly two writers, both in this repo:

| Writer | What it writes |
|---|---|
| `nx_lib/views/generali/` | the effort-logging tables (CRUD from the tenant pages) |
| `scripts/generali-import/{local,remote}/csvToSql.ps1` | `Documents`, `DocumentSapMetadata`, `ImportRuns` — the daily CSV import |

**The importer is not deployed by `deploy.yml`.** Both copies live in this repo
but the one that actually runs sits on `prdimpexp01` and is copied there by
hand. Anything that changes the shape of `Documents` has to be coordinated with
that copy — see `scripts/generali-import/README.md` for the deploy order.

---

## The naming rulebook

Until 2026-09 this database was half German, half English, in three casing
styles, with every column typed `varchar(100)`. Issue #220 restructured it.
The rules below are what it was restructured *to*; follow them for anything
new, and prefer fixing a violation over adding a parallel style.

```
Tables       PascalCase, English, plural            Documents, DocumentTypes, ImportRuns
Views        v + table name                         v_Documents
Columns      PascalCase, English, no prefix         ScannedAt, PolicyNo, RecipientId
Keys         Id                                     Documents.Id
Foreign keys <EntitySingular>Id                     DocumentTypeId, CurrencyId
Booleans     Is/Has prefix                          IsPending
Dates        <Verb>At for datetime, <Noun>Date      ScannedAt, ImportedAt, VoucherDate
Numbers      No unit in the name unless ambiguous   EffortHours, Amount, Quantity
Text keys    …No for business numbers               PolicyNo, ClaimNo, ContractNo
Constraints  PK_/FK_/UQ_/IX_ + table + columns      IX_Documents_ScannedAt
```

Abbreviations are spelled out **except** the ones Generali itself uses as
words: `Iss`, `Sap`, `Gav`, `Gpv`, `Rgi`, `Syrius`.

Constraints are always named explicitly. Auto-generated names
(`PK__Dokument__3214EC271A02B9B9`) differ between INT and PROD, so they churn
the generated DDL under `sql/GeneraliDB/` on every re-dump and make migrations
that reference them environment-specific.

---

## Shape

### `Documents` — the whole dataset

One row per scanned document, 2.7M rows, 66 columns, deliberately **one wide
denormalised table**. It is a reporting landing table with a 1:1
row-to-document mapping; normalising it would buy nothing and break every
report.

| Index | Why |
|---|---|
| `PK_Documents` (`Id`) | clustered surrogate |
| `UQ_Documents_DocumentId` (`DocumentId`) **filtered** `WHERE DocumentId IS NOT NULL` | what the daily `MERGE` matches on |
| `IX_Documents_ScannedAt` `INCLUDE (…9 lookup ids)` | every report filters on the scan date; the INCLUDE list covers the two group-bys the pages issue |

The filter on `UQ_Documents_DocumentId` is load-bearing, not decoration: the
importer deliberately admits rows with a NULL `DocumentId`
(`WHERE rn = 1 OR [DocumentId] IS NULL`). It is also why the column cannot be a
foreign-key target — SQL Server will not accept a filtered index as one, which
is why `DocumentSapMetadata` keys on `DocumentRecordId → Documents.Id` instead.

**Typed columns are computed, not stored.** The CSV arrives as strings and the
string is kept as the truth; the typed reading sits beside it as an expression:

| Computed | Over | Rule |
|---|---|---|
| `Amount decimal(18,2)` | `AmountText` | strip `'`, spaces; `,` → `.` |
| `Quantity decimal(18,3)` | `QuantityText` | `,` → `.` |
| `VoucherDate date` | `VoucherDateText` | style 104 (`dd.MM.yyyy`) |
| `IsPending bit` | `PendingText` | `'True'`/`'False'`, anything else NULL |

A backfilled column is right on the day it ships and wrong from the next import
unless the importer is taught to write it too; one expression cannot drift.
They are not `PERSISTED` — nothing to add, no lock, no storage — but the
expressions are deterministic and precise, so `PERSISTED` is a one-line upgrade
if a report ever wants an index on one.

Do **not** drop the `*Text` columns. They are the data, not a legacy copy of it.

### The 14 lookups

`CommunicationTypes`, `Currencies`, `Directions`, `DocumentStatuses`,
`DocumentTypes`, `InboundChannels`, `InterfaceLinks`, `Languages`,
`NotificationStatuses`, `Origins`, `PostChecks`, `Recipients`, `ScanLocations`
— each `(Id, Name)`, each with a real FK from `Documents`
(`PostChecks` twice, as `PostCheck1Id` / `PostCheck2Id`).

They stay **separate typed tables** rather than one polymorphic `CodeList`. A
single lookup table cannot express "this column may only reference rows of kind
X" without composite-key tricks, and the FK graph is what makes the diagram and
the joins readable. Thirteen tiny tables is not a cost.

### `v_Documents`

The resolved view: `Documents` with all 14 lookups joined to their text. The
app reads this in all 12 of its document queries and never touches `Documents`
directly, and it is the base object of the `generali_documents` reporting
source.

> **It is not the whole table.** `v_Documents` carries
> `WHERE InterfaceLinks.Name = 'CaptivaCapture'`, inherited from the view it
> replaced. That is ~900k of the 2.7M rows. Anything that needs the full set
> has to go to `Documents`.

### The effort cluster

Five small tables the tenant pages write, plus two catalogues:

| Table | Rows | Shape |
|---|---:|---|
| `AttendanceEntries` | 10 | `EffortInHours`, `UserID`, `ForDate`, parent/sub category |
| `BaseServiceEntries` | 2 | `EffortInHours`, `UserID`, `ForDate`, `Category` |
| `ProjectEntries` | 3 | `EffortInHours`, `UserID`, `ForDate`, `Category`, `Comment` |
| `QualityCheckEntries` | 5 | `Quantity`, `UserID`, `ForDate`, three category levels |
| `IssReports` | 6 | `ReportForDate`, `ReportByUserID`, `OnTime`, `Category` |
| `EffortCategories` | 32 | catalogue: `(ParentCategory, SubCategory)` pairs |
| `QualityCheckCategories` | 27 | catalogue: `(ParentCategory, ParentSubCategory, SubCategory)` |

These four entry tables look mergeable and are deliberately **not merged** —
see "Decisions that look wrong" below.

Note the catalogues are *combination* tables, not `(Id, Name)` catalogues: 32
effort rows carry only 6 distinct parent categories.

### `CategoryTerms`

One row per distinct German category term, with a column per locale:
`(Id, NameDe, NameEn, NameFr, NameIt)`, 53 rows. `NameDe` is unique and is what
the catalogue tables and the entry rows actually store; the endpoint hands the
browser a `{German: localised}` map and the page substitutes on render.

Because the lookup happens in JavaScript by exact string, **trailing whitespace
in a category value is a bug**, and a bug SQL Server hides: `=`, `<>`, `GROUP
BY` and `DISTINCT` all ignore trailing spaces, so `'x '` and `'x'` compare
equal everywhere except in the browser. Audit with `DATALENGTH`, never with
`col <> LTRIM(RTRIM(col))` — the latter is always false. Migration `0015` fixed
the seven rows that had this.

### `DocumentSapMetadata`

1:1 side table, 3.7k rows, for the six SAP fields that are populated on 0.14%
of documents. Keyed `DocumentRecordId → Documents.Id` (see above for why not
`DocumentId`). The importer writes it with a second `MERGE` after the main one;
SAP data is still arriving, so this is live, not an archive.

### `ImportRuns`

One row per CSV import run — `Status`, row counts, `MinScannedAt`/`MaxScannedAt`
and durations, written by `csvToSql.ps1`. First place to look when a report
goes empty.

---

## Decisions that look wrong

**Four near-identical effort tables are not merged into one.** They hold 20
rows between them and the obvious move is one `EffortEntries` with an
`EntryType` discriminator. Two reasons not to:

1. The payoff was already collected elsewhere. The four tables used to have
   four ~200-line CRUD blocks; `nx_lib/views/generali/_crud.py` is now a
   descriptor-driven factory and each page contributes only a `CrudTable`.
   Merging the tables saves no application code.
2. It would collapse a permission boundary. `generali_attendance`,
   `generali_baseservices`, `generali_projects` and `generali_pdqm` are four
   reporting sources with four separate `reporting.source.*.use` grants, and
   they are separate *only* because they name four different objects.
   `ReportingSources` has no predicate column — `_quote_object()` in
   `nx_lib/reporting/table_query.py` splits `BaseObject` on dots and
   bracket-quotes each part, so a `WHERE` cannot ride along in it, and the
   Simple-tab filters are the user's, chosen at run time. Point all four at one
   table and a PDQM grant reads attendance hours by default.

Merge them the day `ReportingSources` grows a source-level filter, not before.

**The 13 lookups have no per-locale name columns.** Nothing translates them
today: the app reads their German text through `v_Documents` and shows it as-is.
Adding `NameEn`/`NameFr`/`NameIt` would ship ~250 empty columns waiting for
translations nobody has written. Add them the day someone supplies the
translations.

**`Documents` columns are still `varchar(100)` regardless of content.** 34 of
them hold ≤ 20 characters and the widest value in the table is 148. Narrowing
is a size-of-data operation across a 2.7M-row table — a long, log-heavy write
for an optimizer-estimate gain nobody has asked for.

**`AmountText` is not money.** Of 9,531 non-blank values, 9,183 are the literal
`'CH04'` and the rest `'CH00'`, `'CH70'`, `'LI00'`, `'CH96'` — IBAN country-
and-checksum prefixes. Only 207 are numbers. `Amount` therefore exists and is
97.8% NULL. No cleaning rule fixes this; the source system is writing the wrong
field, and it is worth raising with Generali rather than papering over.

---

## Changing the schema

Same rules as everywhere else in this repo — a migration under
`sql/_migrations/GeneraliDB/NNNN_*.sql`, applied by `scripts/db-migrate.py`,
never a hand-edit of `sql/GeneraliDB/` (generated from INT). Full walkthrough:
`docs/howto/db-migrations.md`. Two things specific to this database:

**Renames need a compatibility view in the same migration.** `deploy.yml`
applies migrations to PROD *before* it stops the app pool, so for a few seconds
the old code runs against the new schema. Every rename in #220 shipped with a
view under the old name, and the views came out one release later (`0014`).

**Filtered indexes and views need the right SET options.** `sqlcmd` leaves
`QUOTED_IDENTIFIER` OFF, and both filtered indexes and `CREATE VIEW` require it
ON. Start any migration that creates either with:

```sql
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
```

**A filtered index is a column dependency.** `sp_rename` on a column refuses
(Msg 5074) while a filtered index mentions it in its predicate, even though the
same rename works fine under an ordinary index. Drop the index, rename, then
recreate it under the new name.

**Rename constraints by matching table and column, never by current name.**
Auto-generated names differ between INT and PROD, so a migration that hardcodes
`PK__Dokument__3214EC27…` works on one environment and fails on the other.
Drive it from `sys.key_constraints` / `sys.foreign_keys` instead.
