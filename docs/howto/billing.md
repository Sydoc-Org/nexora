# Sydoc Billing: what was invoiced in Bexio

`/billing?month=YYYY-MM` shows what Sydoc invoiced in **Bexio**, per Finance
client. Each invoice is shown with its lines, next to the **Sydoc Finance
figures of the month it bills**. The page also lists the invoices to Bexio
contacts that no client is linked to, and everything still owed across all
months. It is the third page of Sydoc's own books, next to Finance
(`docs/howto/finance.md`) and BPS (`docs/howto/bps.md`), and it replaces the
Bexio panel that sat on Finance (#423).

- Issue #436. Design: `docs/design/design_handoff_sydoc_billing/` (README and
  the `Sydoc Billing.dc.html` prototype).
- Permission: `billing.view`. Migration `0147` grants it to every profile and
  user override that holds `finance.view`.
- Read-only against Bexio: `nx_lib/bexio.py` only searches and GETs. Prices and
  amounts are Bexio's; nexora keeps none.

## The month is the invoice month

`/billing?month=2026-09` lists the invoices **dated** (`is_valid_from`) in
September 2026. These invoices bill **August**, which is the Finance month
`month − INVOICE_MONTH_OFFSET` (`nx_lib/bexio.py`, currently 1). The rule is
`billing.billed_month()`.

- The default is the **previous** calendar month, the same as Finance. On
  1 October that is September, the invoices for August. The current month is
  one click on ›, flagged *Running*.
- The oldest pickable month is the one that bills Finance's oldest month, so
  every invoice month has a billed month to compare with.

## The page

- **Band.** It shows:
  - *Bills*: the billed month, closed (lock) or open.
  - *Source*: when Bexio was read (the cache time).
  - The totals: invoiced in CHF, excl. VAT, the number of invoices (with
    drafts and cancelled invoices named apart), clients invoiced out of the
    clients with a Bexio link (as in the picker), and other currencies.
  - The jump index. A linked client with no invoice that counts (missing or
    draft only) gets an amber dot.
  - *Sydoc Finance* opens Finance on the billed month (only for
    `finance.view` holders). *Refresh* bypasses the caches.
- **One row per Finance client** (`Section.client`, in Finance order; Sydoc's
  own services are billed on the customers' invoices and have no row). The row
  shows:
  - The client's Bexio contacts and a state: *Invoiced*, *Draft only*,
    *No invoice in {month}*, or *No Bexio contact linked*.
  - Each invoice in date order with its **lines expanded**: text, quantity,
    unit price, discount (only when a line has one), total, then excl. VAT, VAT
    and total. Under it come the date, due date, the part-payment state, a note
    for a cancelled, draft or foreign-currency invoice, and the **PDF** and
    **Open in Bexio** buttons. A cancelled invoice is struck through, with its
    lines collapsed.
  - A client without an invoice names its latest earlier invoice and its
    status.
  - Below, at full width, the **Finance figures of the billed month**. A client
    with several sections (Privera) gets one column per section. Its billed BPS
    hours (each booking rounded up to ¼ h, split per invoice as in the BPS
    export) are labelled *Billed hours (BPS)*.
- **Ticks** (✓). An invoice line whose quantity **exactly equals** one of the
  client's figures gets a tick, and so does that figure. Hours match hours and
  counts match counts; a line with no unit may match either. Cancelled and
  draft invoices are not matched. There is no line-to-figure mapping, so this is a
  **heuristic** and the hint says so. The matching runs in `static/js/billing.js`
  (`matchTicks`) once both sides have loaded.
- **Other Bexio contacts.** Invoices dated in the month to contacts that no
  Finance client is linked to. They are listed with their contact and kept out
  of every total. A contact that belongs to a client is linked by a migration
  into `dbo.FinanceBexioContacts` (see below).
- **Open and unpaid.** Every Bexio invoice with status open (8), partly paid
  (16) or unpaid (31), **whatever its month**, oldest due date first. The open
  amount is Bexio's `total_remaining_payments`, and overdue means due before
  today. The KPI strip shows CHF outstanding and CHF overdue, with each other
  currency in its own tile. Nothing is converted.
- **Month picker.** Each past month says *All invoiced* or *n missing*: how
  many linked clients have no invoice that counts, dated in it. Clients with no
  link are not checked. The states come from one Bexio search over the viewed
  year (`/api/billing/months`, cached 30 minutes). If that search fails, the
  months show plainly.
- **Print** prints the lines expanded, without buttons, jump index or arrows.

## Where the data comes from

| What | Source |
|---|---|
| Invoices of the month | `bexio.search_invoices(window)` → `reconcile()` (clients, `others`, totals) |
| Their lines | `bexio.invoices(ids)`: one GET per invoice, 4 in parallel, each cached. A failed read shows its reason in place of that invoice's lines |
| A missing client's latest invoice | `bexio.latest_before(contacts, first day)`. Bexio orders a search by id only, not by date, so the newest 50 by id are read and the latest date wins |
| Finance figures | `/api/billing/figures/<section>`: the same section payload Finance serves (`_section_payload`), or its **month-close snapshot** when the billed month is closed, reduced by `billing.section_figures()`. The `bps` section answers with `billing.billed_hours()` per client |
| Outstanding | `bexio.search_outstanding()` → `outstanding()` |
| Contact ↔ client | `dbo.FinanceBexioContacts` (`0141`, links in `0143`): one row per contact, so a contact belongs to one client and a client may have several |

Bexio is read live and is **not part of the Finance month close**: Bexio is the
system of record for the invoice. Bexio results are cached for five minutes
in-process; *Refresh* bypasses the cache.

## Token

`BEXIO_PAT` in `env/<ENV>.env`. If it is unset, the page says *not
configured* and nothing calls Bexio. A rejected token or a Bexio outage shows
its reason under the band while the Finance figures still render. To check a
token, read-only:

```
.venv\Scripts\python.exe scripts\bexio-probe.py INT
```

## Routes

| Route | Gate | What |
|---|---|---|
| `GET /billing?month=` | `billing.view` | the page (`month` = invoice month) |
| `GET /api/billing/month?month=[&fresh=1]` | `billing.view` | `window`, `billed {month,label,name,closed}`, `readAt`, `clients[{client,key,contacts,state,invoices[…positions],last?}]`, `others`, `othersTotals`, `totals`, `drafts`, `cancelled`, `count` |
| `GET /api/billing/figures/<key>?month=` | `billing.view` | `{figures:[{label,value,unit}]}` of one Finance section for the billed month (`bps`: `{hours:{client:[…]}}`); `closed` says whether it came from the snapshot |
| `GET /api/billing/outstanding[?fresh=1]` | `billing.view` | `invoices` (sorted by due, `client` or `contact` + `linked`, `overdueDays`), `totals` per currency, `overdue` |
| `GET /api/billing/months?year=` | `billing.view` | `{year, states: {'YYYY-MM': 'running' \| 'all' \| 'missing:<n>'}}` |
| `GET /api/billing/invoice/<id>` | `billing.view` | one invoice with its lines |
| `GET /api/billing/invoice/<id>/pdf` | `billing.view` | its PDF, inline, `no-store` |

The old `/api/finance/bexio*` routes are gone.

## Key files

| What | Where |
|---|---|
| Bexio client (read-only), reconciliation, outstanding, month states | `nx_lib/bexio.py` |
| Invoice month ↔ billed month, client rows, figure reduction | `nx_lib/billing.py` (pure) |
| Routes | `nx_lib/views/billing.py` |
| Page, JS shim, behaviour, styles | `templates/billing.html`, `templates/js/_billing_js.html`, `static/js/billing.js`, `static/css/billing.css` (on top of `finance.css`, whose ledger rows, group heads and jump index it reuses) |
| Permission | `sql/_migrations/NexoraDB/0147_billing_page.sql`, `sql/test/seed.sql` |
| Sidebar group *Sydoc internal* (Finance, BPS, Billing, Controlling) | `templates/_header.html`, generic `data-nx-nav-group` wiring in `static/js/header.js` |
| Tests | `tests/unit/test_bexio.py`, `tests/unit/test_billing.py`, `tests/integration/test_billing_routes.py` |

## Gotchas

- **Which invoice bills which month** is an assumption (`INVOICE_MONTH_OFFSET`).
  The band names both months, so a wrong offset is visible rather than silent.
- **Ticks are exact.** A rounded quantity (an invoice billing 4,190 of 4,192
  documents) gets no tick, and a coincidental equality gets one. Read a tick as
  "worth a glance", not as proof.
- Bexio's `order_by` takes `id` / `id_desc`, not `is_valid_from` (HTTP 400).
  Every date order is applied in nexora.
- Jinja's `_()` %-formats every msgid, so a shim string may not end in a bare
  `%` (it raises *incomplete format*). The VAT label is `"VAT {rate}"`, and the
  JS appends the `%`.

## Where the build differs from the design

- **Own permission.** The design assumed `finance.view`. Billing has
  `billing.view` (`0147`), so the Finance figures come from Billing's own
  `/api/billing/figures/<key>` rather than `/api/finance/section/<key>`, which
  is gated by `finance.view`.
- **Shared CSS stays in `finance.css`.** The design suggested promoting the jump
  index, group heads and ledger rows into `nexora-ui.css` as `nx-sydoc-*`. The
  page loads `finance.css` instead, and `billing.css` adds the rest.
- **Controlling is in the group** as a fourth item (#433 landed while this
  was built), and the group is called *Sydoc internal*, not *Sydoc*: INT has a
  tenant named Sydoc whose group would sit next to it.
- **No "paid {date}".** A Bexio invoice search carries no payment date, so the
  meta row shows the date, the due date and, for a partial payment, the paid
  and open amounts.
