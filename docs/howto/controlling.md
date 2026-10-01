# Sydoc Controlling: margin per client

`/controlling` shows, for each client stream and month, what the work cost and
what it earned. The cost is the BPS hours times the hourly rate, plus any
external costs. The earnings are the Bexio invoices excluding VAT. The difference
between them is the margin. The page replaces the hand-filled
`Projektcontrolling_Betriebskosten.xlsx` (`R:\01_GL\01_02_Finance_Controlling\Controlling\`),
which had one sheet per stream plus an Overview tab with one column per month.
Details:

- issue: #433; design: `docs/design/design_handoff_sydoc_controlling/` (turn 1a)
- permissions: `controlling.view` reads the page, `controlling.rates.edit` edits
  rates and external costs (both Global Admin only, like `finance.view`)
- migrations: `0145` (permission, rates, Bexio project map), `0146`
  (corrections from reconciling against the workbook) and `0147`
  (`controlling.rates.edit`, the month-close snapshot)
- the third page of Sydoc's own books, next to Sydoc Finance
  (`docs/howto/finance.md`) and Sydoc BPS (`docs/howto/bps.md`)

**Files:** rules in `nx_lib/controlling.py` (pure), routes in
`nx_lib/views/controlling.py`, the workbook export in
`nx_lib/controlling_export.py`. The page is `templates/controlling.html` with its
shim `templates/js/_controlling_js.html`, behaviour in `static/js/controlling.js`
and layout in `static/css/controlling.css`. It also loads `finance.css` for the
shared ledger pieces.

**Page, top to bottom:**

1. **Band:** Excel, Print and Rates buttons; month headline and picker; Status
   and Rate stats.
2. **Month summary:** hours, cost, invoiced, margin and documents, each with
   its change against the previous month.
3. **Margin by client:** one row per stream with a diverging margin bar, flags,
   unassigned invoices and a total row.
4. **Per-client blocks:** one open at a time. Each holds the hours and cost by
   task (*Aufwendungen nach Tätigkeit*), the Bexio invoice lines
   (*Debitor-Positionen*), the difference (*Differenz*) and per-unit figures.
5. **Hours by task:** a task × stream heat matrix with an FTE row.
6. **Document volumes.**
7. **Trend:** total margin, hours and documents per month, plus one small chart
   per stream, with a shared hover.
8. **Rates drawer:** default rate, per-stream overrides, hours per FTE day and
   the month's external costs.

## Streams

There are ten streams, one per workbook sheet. `nx_lib/controlling.py` (`STREAMS`)
is the single definition.

| Stream | BPS hours (customer · package) | Bexio projects | Documents (Finance figure) |
|---|---|---|---|
| Elektro-Material | Elektro Material · all | 8 | `em_documents` |
| Compass Group | CompassGroup · all | 5 | `compass_documents` |
| Privera Posteingang | Privera · Posteingang, Tagesgeschäft Posteingang, **plus Zupfen on any package** | 10 | `privera_posteingang_documents` |
| Privera Rechnungseingang | Privera · Invoice, Tagesgeschäft Invoice | 4 | `privera_documents` |
| Privera Neuzugänge | Privera · Neuzugänge, Tagesgeschäft Neuzugänge | 17 | `privera_neuzugaenge_dossiers` |
| Frigemo | Frigemo · all | 58 | `frigemo_imported_docs` |
| ZHAW | ZHAW · all | 7 (Aveniq), 74 (Xpert) | `xpert_stats_documents` where Client = ZHAW |
| BFH | BFH · all | 33 (BFH direct) | `xpert_stats_documents` where Client = BFH |
| Bucherer | Bucherer · all | 32, 43, 45 | `bucherer_easytax_imported` |
| MediaMarkt | MediaMarkt · all | 12 | `mediamarkt_pieces` |

Each rule is copied from the workbook, which is the truth (#433):

- **Zupfen counts under Posteingang.** BPS books Privera's Zupfen on
  `Tagesgeschäft Invoice`, but the workbook has always counted it under
  Posteingang (`REASSIGN`).
- **Aveniq's packages are on no stream.** Its packages (BFH, ZHAW, HAP, BAC, …)
  are the DocProStar mandants. The workbook counts neither their hours nor the
  DocProStar invoices (projects 6 and 73).
- **Postpakete are not revenue.** Project 46 is postage passed through at cost.
- **Every hour counts.** All BPS hours on a stream count, Pause and internal
  support included, as in the workbook. This is not the Finance page's billable
  rule.
- **Jan–Oct 2025 Privera hours are incomplete.** BPS has fewer Privera hours for
  those months than the workbook, and the missing bookings were never in the
  timetool. The page shows the BPS hours with the **incomplete** flag
  (`INCOMPLETE`) rather than inventing numbers.

## Inputs

| Input | Where | Read by |
|---|---|---|
| Hours | `bps_projects` reporting source (`BPS_ProjectReportAll`), grouped by month · customer · package · task | `controlling.hours_query` |
| Rates | `dbo.FinanceRates`: `hourly` (CHF/h) and `fte_day_hours` (hours per FTE working day). `StreamKey` NULL is the default; a stream row overrides it. `ValidFrom`/`ValidTo` are months, and the latest start wins | `rate_for` |
| Invoices | Bexio, live; the invoice for month M is dated in M+1 | `assign_invoices` |
| Invoice → stream | `dbo.ControllingInvoiceStreams` (per invoice) beats `dbo.ControllingStreamProjects` (per Bexio project). StreamKey NULL = excluded on purpose | |
| External costs | `dbo.ControllingCosts` (entered by hand) plus Bexio purchase bills whose vendor matches `dbo.ControllingVendorStreams`, in their bill month | `bill_costs`, `fold_costs` |
| Documents | the Finance section's source and month basis, or the Finance **month-close snapshot** when that month is closed (the live count rides along as `documentsLive` when it moved) | `documents_queries`, `snapshot_documents` |

Invoices are matched by **project, not title.** Privera's three invoices, and
their three support invoices, all carry titles like "September 2025". Only the
Bexio project tells them apart. Where Bexio tagged an invoice with the wrong
project, add a row to `ControllingInvoiceStreams` through a migration. 0146 seeds
RE-26780, a Rechnungseingang support invoice on the Posteingang project.

**Foreign currencies are not converted** (design review). Bucherer is billed
mostly in EUR. An issued invoice in another currency makes the stream month
`foreign`:

- the amount shows in its own currency (`foreign`);
- the month gets no margin;
- the amount stays out of every total.

## Month close

A month that Sydoc Finance closes is closed here too.
`views/finance.close_month` calls `views/controlling.close_month`, which
freezes every stream's figures (hours, tasks, rate, cost, invoiced amounts,
margin, documents) as one JSON row in `dbo.ControllingMonthClose`.
`controlling.snapshot` builds that row.

- **Reopening** the month in Finance deletes the row.
- **A source down at close time** (BPS or Bexio) means no snapshot. Finance's
  close still succeeds, and the month stays live here. This is logged.
- **A closed month is served from the snapshot.** Rate changes and corrected
  invoices no longer move it. The Bexio invoice lines stay live. Where Bexio's
  amount now differs from the snapshot, the stream gets the `moved` flag, its
  live figures appear in `live`, and the page shows Finance's drift note.
- **Months Finance closed before 0147** have no snapshot.
  `scripts/controlling-freeze-months.py --env <ENV> [--dry-run]` freezes them.
  It can be re-run safely.

## States and flags (never a silent 0)

Each stream month has a `state` that says whether it has an amount:

| `state` | Meaning |
|---|---|
| `invoiced` | an issued invoice counts (drafts and cancelled ones don't) |
| `draft` | only drafts so far |
| `missing` | no invoice yet |
| `unlinked` | no Bexio project is mapped to the stream |
| `foreign` | an issued invoice in another currency (shown, not converted, not summed) |
| `error` | Bexio could not be read |

Margin is only computed for `invoiced`. It also needs a valid rate (`no_rate`
flag otherwise) and a known external cost (`cost_unknown` flag otherwise).

Other flags:

- `incomplete`: see above.
- `override`: a per-stream rate applies.
- `no_hours`: invoiced, but nothing booked.
- `bps_error`: BPS could not be read. Hours, cost and margin are unknown, but
  the invoices still show.
- `moved`: a closed month whose Bexio amount changed since the close.

A draft-only month carries the draft amount (`draft`), which the page shows as
"+x if issued as drafted".

Lists reported next to the table:

- **Unassigned invoices:** invoices to a linked Finance contact that no rule maps.
- **Hours on no stream:** unmapped BPS bookings of the streams' customers.

Totals add up only the streams that have a margin, and say how many those are
(`streamsWithMargin` / `streams`).

## API

| Route | Gate | What |
|---|---|---|
| `GET /controlling?month=YYYY-MM` | `controlling.view` | the page (default: the previous month; earliest Jan 2025) |
| `GET /api/controlling/month?month=` | `controlling.view` | the whole month: `streams` (`cur`, `prev`, `delta`, invoices with lines), `totals`, `tasks` (task × stream matrix + FTE; `null` when BPS is down), `unassigned`, `unmapped`, `state`, `closed`, `bexioError`, `hoursError`, `costsError`. `fresh=1` bypasses the Bexio cache |
| `GET /api/controlling/trend` | `controlling.view` | per stream and month from Jan 2025 to the current month, plus monthly totals and month states; cached 5 min per process |
| `GET /api/controlling/rates` | `controlling.view` | the rate rows |
| `POST /api/controlling/rates` · `PUT`/`DELETE /api/controlling/rates/<id>` | `controlling.rates.edit` | add / edit (`{kind, stream?, value, from, to?}`) / delete a rate. Periods of one scope must not overlap (409); to change a rate from a month on, end the old row and add a new one |
| `POST /api/controlling/costs` · `DELETE /api/controlling/costs/<id>` | `controlling.rates.edit` | add (`{month, stream, label, amount}`) / delete a manual external cost |
| `GET /api/controlling/export.xlsx?month=` | `controlling.view` | Overview, Detail, Hours by task, Volumes |

## Reconciliation against the workbook

Run on 2026-10-01 for Jan 2025 – Aug 2026.

**Matches:**

- From Nov 2025 on, invoiced and cost match the workbook to the cent for every
  stream except Bucherer, whose workbook sheet has no 2025+ figures.

**Known differences:**

- **Privera Rechnungseingang:** the workbook has 13–80 CHF/month more revenue,
  from small lines typed into the sheet that are not on the invoices.
- **Missing invoices in the workbook:** a few single support invoices (46–2,722
  CHF, 2025) are missing from the workbook. Bexio wins.
- **Digi-Texx Jun 2026:** neither the workbook nor Bexio has the June 2026
  Digi-Texx cost. Add it as a manual cost once known. Jul and Aug 2026 come from
  the Bexio bills, which the workbook no longer recorded.
