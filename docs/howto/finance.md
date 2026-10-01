# Sydoc Finance — the monthly accounting report

`/finance` shows the figures Sydoc's accounting invoices every month: one section
per billed client, one month at a time, with each figure compared to the month
before. It replaces walking the same numbers out of Reporting report by report.
Issue #408; permission `finance.view`; migration `0138` (the code, its Global
Admin grant, and one extra BPS measure). #415 made the figures match the
workbooks exactly, added the month close and lists the billable BPS bookings
singly (migration `0139`); every BPS hour, drilled down, is on the Sydoc BPS page
(`docs/howto/bps.md`).

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
| Privera · Posteingang | `privera_posteingang` | `ExportDatetime` (text) | documents | per branch; register × branch |
| Privera · Rechnungseingang | `privera_invoice` | `ExportDate` | documents total / mail / eBill | per Mandant, per source |
| Privera · Physische Zustellung | `privera_nachsendungen` | `ExportDatetime` | forwardings total / without TEC | per branch; forwarding type × branch |
| Privera · Neuzugänge | `privera_neuzugaenge` | `JahrExport` + `MonatExportNr` | dossiers / registers / pages | per branch |
| Frigemo | `frigemo` | `DCD` | imported/exported documents and pages, invoices, deleted | – |
| Aveniq · Xpert | `xpert_stats` | `ExportDate` | documents | per client; below it BFH (every metric) and ZHAW (every metric and dimension) side by side (`0144`) |
| Bucherer · EasyTax | `bucherer_easytax` | `ImportTime` (imported, pages) / `ExportTime` (exported) | imported documents, pages, exported documents | – |
| MediaMarkt | `mediamarkt_batches` | `ScanDate` | batches, pieces | per type (K/D/KA) |
| Sydoc · Billable services | `bps_projects` | `Datum` | billable hours, billed hours (¼ h), billable bookings | every booking, per customer, with its comment; hours per task |

The first six are the #329 workbooks (internal customers); the next four are
the external clients whose collectors already fill a Statistics table — what
exists, shown the way it makes sense for a monthly bill. The last one is the
Sydoc services billed per booking: every **billable** BPS booking of the month
(`0124`'s `bps_projects` source, which reads `BPS_ProjectReportAll` since `0142`
— history from January 2025), one line each with date, package, task, person,
hours and comment, grouped per customer with a subtotal. BPS has no billing
flag; the rule lives once in `nx_lib/bps.py` (`BILLABLE_RULES`, shared with the
BPS page):

- tasks `Support-verrechenbar`, `Support extern verrechenbar`, `Change`,
  `Change Request`, `Professional Services`, `Projektmanagement` on any customer
  except `sydoc` / `sydoc intern`;
- plus `Vorbereitung Akten`, but only on `Privera` · `Tagesgeschäft Neuzugänge`.

Only the **customers of this page** are listed (`Bookings.customers` in
`nx_lib/finance.py`, BPS name → page client: `Elektro Material`, `CompassGroup`,
`Privera`, `Frigemo`, `Aveniq`, `Bucherer`, `MediaMarkt`); billable work for
anyone else (SSD, Generali, the MobScan customers) stays on the BPS page. A new
billed client needs its BPS name added there.

Each booking is **billed rounded up to the quarter hour**, on its own
(`bps.billed_hours`: 0.33 h → 0.5 h, 0.25 h stays). The page shows both: a
*Billed hours* figure next to the booked one, a *Billed* column in the task and
customer tables, and "0.33 h → 0.50 h" on every booking. The previous month's
billed figure is summed from its rows, since no aggregate can round per row.

**Xpert, BFH and ZHAW** are billed per metric of `dbo.Xpert_Stats`, so the
section lists them one by one (a `Breakdown` with `where`, `then` and fixed
`keys`, over the unfiltered `xpert_stats_count` measure of `0144`). Nothing is
filtered away: BFH shows every metric (Total, NeueKreditoren, NKReproduzierte,
Uebrige, UEReproduzierte first, 0 when the month has none, then anything else),
ZHAW every metric and dimension (Total, WorkItems, WorkItemsByEingang · MAIL /
Scanner / (blank), WorkItemsByIsWithOrder · 0 / 1, then anything else). The
lists have no total (Total already is one). `Breakdown.row` puts the per-client
table on its own row and the two lists side by side below it; the BFH new
creditors and ZHAW workitems figures are gone, as is the per-database table.

The Reporting filter grammar only ANDs, so each rule group is its own row query
and the groups are disjoint by construction; the figures come from separate
aggregates, so a list cut at 5,000 rows still totals correctly.

## Parity with the workbooks (#415)

Reconciled against PROD and the published workbooks for May, July and August
2026, figure by figure and, where the workbook has a pivot cache, row by row:

| Section | Result |
|---|---|
| Privera Posteingang, Physische Zustellung, Neuzugänge | exact, every branch; the register × branch and forwarding type × branch matrices of the billed "PRIVERA" sheet are exact cell by cell |
| Privera Rechnungseingang | exact after `0139`: the workbook's Mail pivot drops MAIL rows without a file name, so the measure does too (`FileName IS NOT NULL`) |
| Elektro-Material, Compass | the definitions are exact; the **data** moves after the workbook is refreshed (a re-exported EM document gets a new `ExportEM_dt`, a re-uploaded Compass document a new `UploadDatetime`, so the workbook bills it in both months, the live page once) — which is what the month close is for |
| MediaMarkt | 2026 exact once the two 16 Sep batches were entered (they were placeholder rows); `0139` stops counting placeholders as batches |

Deliberately counted as the workbooks count them, and flagged on the page:
Compass August 2026 has 74 rows without a workitem that repeat a barcode, and
the Neuzugänge view counts a dossier registered under two branches in both.

## Month close

Accounting closes a month once it is invoiced (**Close month**, permission
`finance.month.edit`). Every section is read live; if any cannot be read the close
is refused and nothing is written. Otherwise each section's payload goes into
`dbo.FinanceMonthClose` (one row per month and section, stamped with who and
when, `0139`). From then on:

- the month is served **from the snapshot** — the figures, breakdowns, matrices
  and BPS bookings exactly as invoiced, whatever the sources do later;
- the live figures are still computed next to it and, where they moved, the
  section says so ("live data moved", a collapsible at-close / live-now list);
  `?live=1` on the section API returns the live payload instead;
- the CSV export reads the snapshot too (`sydoc-finance-YYYY-MM-closed.csv`).

**Reopen month** deletes the snapshot; close it again to freeze the new state.
The running month cannot be closed. Labels in a snapshot are frozen in the
closer's language.

The months invoiced before the page existed are closed in one go with
`scripts/finance-close-months.py --env PROD` (`--dry-run` first): every month of
the picker except the newest ended one (`--keep 1`, or `--until YYYY-MM`),
already-closed months skipped, labels in German (`--lang`). It calls the same
`close_month()` as the button.

## The page (#427)

Finance and Sydoc BPS are a mirrored, Sydoc-branded pair (design 1a in
`docs/design/design_handoff_sydoc_finance_bps/`). They share the ink band, the
period headline and the picker shell (`templates/_sydoc.html`,
`static/js/nx_sydoc.js`, the `nx-sydoc-*` rules in `nexora-ui.css`).

- **Band:** the actions (close / reopen, CSV, print), the month as the headline
  with prev/next arrows, the three-state hint, the month's status (running,
  closed by whom, or open) and the load counter of the sections. A **jump
  index** sits flush at its bottom, in page order: Bexio, then one item per
  section (`Section.nav`). It never wraps; where it does not fit it scrolls
  sideways with faded edges. (The design's ellipsis cut every label down to a
  letter or two with twelve entries at 1440px.)
- **Month picker** (the headline button, a modal; `NXSydoc.initPicker` moves
  it to `<body>` because `.nx-main` is a stacking context that would keep it
  under the sidebar): a year of months, each marked
  closed (lock), open or running. The states are rendered server-side into the
  shim (`months` in `NX_FINANCE`): one `SELECT DISTINCT Month` over
  `dbo.FinanceMonthClose`. A month outside `month_options()` is disabled.
- **Ledger rows:** each section is identity left (client, title, source and
  basis, the live / closed / drift state, the section's note, and for BPS the
  "All hours in Sydoc BPS" link) and statement lines right: the figure, this
  month, the month before, and a comparison bar (this month as the fill, the
  month before as an orange tick) with the change in neutral ink. Breakdowns
  and the Privera matrix follow; tables collapse after 12 rows.
- **Billable services:** the figures, hours per task and per customer (each
  customer links to its list), then the bookings as a **timeline per
  customer**, a stop per day, the first four shown, "Show all n" for the rest.

## How a month is selected

- **Default month is the previous calendar month** — the one being invoiced.
  The current month can be picked but is flagged as still running; the future
  cannot. The month sits in the URL (`/finance?month=2026-08`), so a month is
  linkable and the browser's back button works. The prev arrow is inert at the
  oldest pickable month, the next arrow at the current one.
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
it through the `0106` trigger. `finance.month.edit` (`0139`, same grants) closes and
reopens a month.

## Adding a client

1. Register the source and its measures the #329 way (a migration with the
   `ReportingSources` row, its `ColumnsJSON` catalog, the `ReportingMetrics`
   rows and the `reporting.source.<code>.use` permission — `0130` is the model).
2. Add one `Section` to `SECTIONS` in `nx_lib/finance.py`: the source code, a
   `Period` (which column the month follows), the measure codes shown as figures
   and the dimensions to break them down by. `group` picks the run of the page
   it appears in: `internal`, `external` or `services`. `nav` is the short
   label of the band's jump index; leave it out and the title (or else the
   client) is used.
3. `tests/unit/test_finance.py` reads the registry back out of the migrations
   and fails if a section names a column or a measure its source does not carry
   — run it. A misconfigured section also fails **loudly** at run time
   (`FinanceSpecError`) instead of quietly returning a grand total where a
   breakdown should be.
4. Labels: measure names come from the registry in four languages; dimension
   labels and the "by … date" basis strings are `N_()`-marked msgids in the spec
   — run `/nx-i18n` after changing them.

## Invoiced in Bexio (#423)

Above the client sections, a panel shows what was actually invoiced in
**Bexio** for the month, so the counted figures and the billed amounts sit on
one page. It is **read-only** against Bexio: `nx_lib/bexio.py` only searches and
GETs; prices and amounts are Bexio's, nexora keeps none. Drafting invoices from
the page is deliberately not built (it needs the invoicing process and a
go-ahead first).

- **Which invoices.** The invoice for billed month M is assumed to be dated
  (`is_valid_from`) in month **M + 1**: the August page lists invoices dated in
  September. One constant, `INVOICE_MONTH_OFFSET` in `nx_lib/bexio.py`; the
  panel names the window it searched, so a wrong assumption is visible.
- **Per client.** Each Finance client (`Section.client`, Sydoc's own services
  excluded; they are billed on the customers' invoices) shows its invoices
  with number, title, date, status, the amount excl. VAT (`total` minus
  `total_taxes`) and the total, or a flag: *no Bexio contact linked*, *no invoice
  in M + 1*, *draft only*. Drafts and cancelled invoices are listed but never
  counted in the totals. Totals are **CHF only**: Bexio sends no exchange rate
  with an invoice, so a foreign-currency one (Bucherer is sometimes billed in
  EUR) is listed in its own currency but not added in. **Lines** loads the invoice's positions (quantity,
  unit, unit price, discount, total) for comparison with the figures below;
  **PDF** streams the invoice PDF through nexora (`no-store`).
- **Linked contacts only.** The panel shows and totals only invoices to Bexio
  contacts linked to a Finance client; Sydoc's Bexio also bills customers nexora
  has no figures for, and those are left out. The links are stored in
  `dbo.FinanceBexioContacts` (`0141`): one row per contact, so a contact belongs
  to one client while a client may have several (Aveniq is billed as Aveniq AG
  and as Xpert Consulting AG). Migration `0143` seeds them for every client; a
  new client or contact gets its link in a new migration. The links are fixed:
  the page only reads them and nexora has no route that changes them.
- **Live, not frozen.** The panel is not part of the month close: Bexio is the
  system of record for the invoice itself. Results are cached for five
  minutes in-process; **Refresh** bypasses the cache.
- **Token.** `BEXIO_PAT` in `env/<ENV>.env`. Unset, the panel says *not
  configured* and nothing calls Bexio; a rejected token or a Bexio outage shows
  its reason in the panel while the rest of the page renders. Check a token,
  read-only, with:

  ```
  .venv\Scripts\python.exe scripts\bexio-probe.py INT
  ```

  It reports which of the endpoints the panel needs answer. It cannot tell
  whether the token could also write; that is visible only in Bexio.

## What the page does not do (yet)

- It does not write invoices: the Bexio panel reads them, and matching an
  invoice line to a figure is left to the reader.
- Privera's *Mailbestellungen* (a hand-pasted Outlook export) has no source and
  is not on the page.

## Export and print

- **Excel** (`/api/finance/export.xlsx?month=YYYY-MM`, the band's *Excel*
  button) and **CSV** (`/api/finance/export.csv`, no button any more, kept for
  scripts): every figure, every
  breakdown and matrix cell and every billable booking of the month as one flat
  sheet, UTF-8 with BOM so Excel opens it directly; a booking's date, package,
  person and comment are in the `Detail` column. Sections that could not be
  read appear as an `error` line. A closed month exports its snapshot.
- **BPS hours** (`/api/finance/bps-export?month=YYYY-MM&format=xlsx|pdf`, the
  *Export hours* box in the Billable services section): one sheet per invoice
  — per customer, Privera split into Posteingang, Invoice and Neuzugänge
  (`Bookings.split`; "Tagesgeschäft X" counts as X) — with date, package,
  task, person, comment and the billed (rounded) hours with a total; the
  booked hours stay on the page only. `sheet=all`
  (default) is one file behind an overview sheet / page, `sheet=<key>` one
  invoice, `files=separate` a `.zip` with one file per invoice. Built by
  `nx_lib/finance_export.py` (openpyxl, fpdf2 with matplotlib's DejaVu Sans
  for Unicode); a closed month exports its snapshot, and the billed hours are
  recomputed from the booked ones so an older snapshot exports the same way.
- **Print** uses a print stylesheet: sidebar, band actions, arrows, jump index
  and the BPS link hidden, the month headline small and black, one section per
  block, every collapsed table and timeline expanded.

## Files

| What | Where |
|---|---|
| Spec, month arithmetic, query building, payload, snapshot diff | `nx_lib/finance.py` (pure, DB-free) |
| Billable rule (shared with the BPS page) | `nx_lib/bps.py` |
| Routes: page, section API, close / reopen, CSV, BPS export | `nx_lib/views/finance.py` |
| BPS hours as Excel / PDF / zip | `nx_lib/finance_export.py` |
| Closing the past months | `scripts/finance-close-months.py` |
| Xpert count measure | `sql/_migrations/NexoraDB/0144_xpert_stats_count_metric.sql` |
| Page, JS shim, behaviour, styles | `templates/finance.html`, `templates/js/_finance_js.html`, `static/js/finance.js`, `static/css/finance.css` |
| Band, headline, picker shared with BPS | `templates/_sydoc.html`, `static/js/nx_sydoc.js`, `nx-sydoc-*` in `static/css/nexora-ui.css` |
| Permission + BPS measure | `sql/_migrations/NexoraDB/0138_finance_page.sql`, `sql/test/seed.sql` |
| Parity fixes, `FinanceMonthClose`, `finance.month.edit` | `sql/_migrations/NexoraDB/0139_finance_parity_and_close.sql`, `sql/test/schema.sql` |
| Bexio client (read-only), window, reconciliation | `nx_lib/bexio.py` |
| Bexio panel routes: panel, invoice lines, PDF, link / unlink | `nx_lib/views/finance_bexio.py`, `static/js/finance_bexio.js` |
| `FinanceBexioContacts` | `sql/_migrations/NexoraDB/0141_finance_bexio_contacts.sql` (table), `0143_finance_bexio_contact_links.sql` (links), `sql/test/schema.sql` |
| Token check | `scripts/bexio-probe.py` |
| Tests | `tests/unit/test_finance.py`, `tests/unit/test_finance_export.py`, `tests/unit/test_bps.py`, `tests/unit/test_bexio.py`, `tests/integration/test_finance_routes.py`, `tests/integration/test_finance_bexio_routes.py` |

## Gotchas

- The INT copy of the Neuzugänge view used to bind to a `SYDOC_Statistik1` that
  does not exist (a restore artefact, see `0134`), so its section showed the
  driver error in place while the other ten rendered — the designed behaviour
  for any source that is down, not a page failure. Repointed on 2026-09-29 with
  one `ALTER VIEW` on INT's `SYDOC_Statistik` (the stray database prefix dropped,
  nothing else); INT's sample rows do not join, so the section reads zero there.
- INT's Statistics tables are sparse copies; pick a month that has rows before
  concluding a section is broken (Posteingang has July 2025, Compass May 2026,
  MediaMarkt August 2026, …).
- The section API answers a failed source with HTTP 200 and an `error` field:
  the page renders the error where the figures would be. A 404 is only an
  unknown section key.
- `_header.html` loads `nexora-ui.css` a second time, **after** `finance.css`.
  An override of a `nx-sydoc-*` rule in `finance.css` therefore needs a more
  specific selector (`body.nx-sydoc …`, `.nx-sydoc-dot.nx-fin-dot--open`) or it
  silently loses.
- The legacy ODBC driver returns `datetime2` as text: `ClosedAt` is parsed back
  in `views/finance.py` (`_as_datetime`), and shown in Swiss time.
