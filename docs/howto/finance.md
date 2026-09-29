# Sydoc Finance — the monthly accounting report

`/finance` shows the figures Sydoc's accounting invoices every month: one section
per billed client, one month at a time, with each figure compared to the month
before. It replaces walking the same numbers out of Reporting report by report.
Issue #408; permission `finance.view`; migration `0138` (the code, its Global
Admin grant, and one extra BPS measure).

## Where the numbers come from

The page has **no SQL of its own**. Every section names a reporting source that
migrations `0126`–`0137` registered in `dbo.ReportingSources` (all `table`
provider, all on the Statistics server) and the measures `dbo.ReportingMetrics`
carries for it. `nx_lib/finance.py` turns that into report definitions and hands
them to the same builder Reporting's `table` provider runs
(`build_generic_query` over `resolve_metrics`, see `docs/howto/reporting.md`), so
a figure here and the same measure in a report are **one definition, two views**.
The load-bearing quirks of #329 (Elektro-Material's channel filter, Compass
billing on the upload date, Privera's `DocSource` split, "ohne TEC" being a
forwarding type and not a branch) live in the registry rows and are therefore
identical on both pages.

| Section | Source | Month basis | Figures | Breakdown |
|---|---|---|---|---|
| Elektro-Material | `em_invoice` | `ExportEM_dt` | documents (Opex + e-mail), images out, order item positions | per channel |
| Compass Group | `compass_invoice` | `UploadDatetime` | documents | – |
| Privera · Posteingang | `privera_posteingang` | `ExportDatetime` (text) | documents | per branch |
| Privera · Rechnungseingang | `privera_invoice` | `ExportDate` | documents total / mail / eBill | per Mandant, per source |
| Privera · Physische Zustellung | `privera_nachsendungen` | `ExportDatetime` | forwardings total / without TEC | per branch |
| Privera · Neuzugänge | `privera_neuzugaenge` | `JahrExport` + `MonatExportNr` | dossiers / registers / pages | per branch |
| Frigemo | `frigemo` | `DCD` | imported/exported documents and pages, invoices, deleted | – |
| Aveniq · Xpert | `xpert_stats` | `ExportDate` | documents, BFH new creditors, ZHAW workitems | per client, per source database |
| Bucherer · EasyTax | `bucherer_easytax` | `ImportTime` (imported, pages) / `ExportTime` (exported) | imported documents, pages, exported documents | – |
| MediaMarkt | `mediamarkt_batches` | `ScanDate` | batches, pieces | per type (K/D/KA) |
| Sydoc · BPS | `bps_projects` | `Datum` | service hours, absence hours, total hours | per task, per customer |

The first six are the #329 workbooks (internal customers); the next four are
the external clients whose collectors already fill a Statistics table — what
exists, shown the way it makes sense for a monthly bill. The last one is Sydoc's
own time: the hours booked in the BPS timetool (`0124`), per BPS task (Support
verrechenbar, Change, Professional Services, Vorbereitung Akten, …) and per
customer. *Service hours* is a measure `0138` adds — every booking except the
`Absences` pseudo-customer — so the split is registered, not subtracted by hand.

## How a month is selected

- **Default month is the previous calendar month** — the one being invoiced.
  The current month can be picked but is flagged as still running; the future
  cannot. The month sits in the URL (`/finance?month=2026-08`), so a month is
  linkable and the browser's back button works.
- A real date column is a **half-open range** `first <= x < first of next month`,
  bound as ISO strings (`'2026-08-01'`), which is what every Reporting date
  filter binds too. The legacy "SQL Server" ODBC driver on the hosts cannot bind
  a Python `date` at all (`HYC00 optional feature not implemented`), so do not
  "fix" this to date objects.
- Posteingang's `ExportDatetime` is `nvarchar` holding `dd.MM.yyyy HH:mm:ss`, so
  its month is a `contains` on `.MM.yyyy` — the 0135 rule, reproduced exactly.
- Neuzugänge is a view already aggregated per year / month / branch: the month
  is `JahrExport = ? AND MonatExportNr = ?`.
- "vs. previous month" runs the same figures for the month before; a section is
  three to five small aggregate statements, all issued in parallel from the
  browser, one request per section.

## Permission

`finance.view` is a new area (`docs/design/permissions.md`). It is **the whole
gate**: the `table` provider applies no row scoping, so whoever holds the code
reads every billing source on the page. It is for Sydoc's own accounting — it
must **never** be granted to a customer profile, the same rule as the
`reporting.source.<code>.use` codes it reads through (`0136`, #332).
`0138` creates the code and grants it to `Global Admin`; `Enterprise Admin` holds
it through the `0106` trigger.

## Adding a client

1. Register the source and its measures the #329 way (a migration with the
   `ReportingSources` row, its `ColumnsJSON` catalog, the `ReportingMetrics`
   rows and the `reporting.source.<code>.use` permission — `0130` is the model).
2. Add one `Section` to `SECTIONS` in `nx_lib/finance.py`: the source code, a
   `Period` (which column the month follows), the measure codes shown as figures
   and the dimensions to break them down by. `group` picks the run of the page
   it appears in: `internal`, `external` or `services`.
3. `tests/unit/test_finance.py` reads the registry back out of the migrations
   and fails if a section names a column or a measure its source does not carry
   — run it. A misconfigured section also fails **loudly** at run time
   (`FinanceSpecError`) instead of quietly returning a grand total where a
   breakdown should be.
4. Labels: measure names come from the registry in four languages; dimension
   labels and the "by … date" basis strings are `N_()`-marked msgids in the spec
   — run `/nx-i18n` after changing them.

## What the page does not do (yet)

- **It does not freeze anything.** `EM_Invoice` is edited after a month closes
  (values as well as rows — see the 2026-09-14 handoff), so re-opening a closed
  month can show different numbers. The Elektro-Material section says so. A
  "close month" snapshot is the natural next step on top of this page.
- It does not know what was actually invoiced; that confirmation is what keeps
  #329's question open, and the page only makes the comparison easier.

## Export and print

- **CSV** (`/api/finance/export.csv?month=YYYY-MM`): every figure and every
  breakdown cell of the month as one flat sheet, UTF-8 with BOM so Excel opens
  it directly. Sections that could not be read appear as an `error` line.
- **Print** uses a print stylesheet: app chrome hidden, one section per block,
  collapsed tables expanded.

## Files

| What | Where |
|---|---|
| Spec, month arithmetic, query building, payload | `nx_lib/finance.py` (pure, DB-free) |
| Routes: page, section API, CSV | `nx_lib/views/finance.py` |
| Page, JS shim, behaviour, styles | `templates/finance.html`, `templates/js/_finance_js.html`, `static/js/finance.js`, `static/css/finance.css` |
| Permission + BPS measure | `sql/_migrations/NexoraDB/0138_finance_page.sql`, `sql/test/seed.sql` |
| Tests | `tests/unit/test_finance.py`, `tests/integration/test_finance_routes.py` |

## Gotchas

- On INT the Neuzugänge view is broken (it binds to a `SYDOC_Statistik1` that
  does not exist, `0134`); its section shows the driver error in place while
  the other nine render. That is the designed behaviour for any source that is
  down, not a page failure.
- INT's Statistics tables are sparse copies; pick a month that has rows before
  concluding a section is broken (Posteingang has July 2025, Compass May 2026,
  MediaMarkt August 2026, …).
- The section API answers a failed source with HTTP 200 and an `error` field:
  the page renders the error where the figures would be. A 404 is only an
  unknown section key.
