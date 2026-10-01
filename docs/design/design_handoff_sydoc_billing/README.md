# Handoff: Sydoc Billing, Bexio as its own page

## Overview
Today the Bexio invoice panel (#423) sits at the top of **Sydoc Finance** (`/finance`). This change moves it to a page of its own, **Sydoc Billing**, and takes it off Finance completely. It is the third page of Sydoc's own books and shares the ink band, the period headline and the month picker with Finance and BPS. In the sidebar, Finance, BPS and Billing move into one collapsible **Sydoc** group.

Billing also does more than the panel did:
1. Each client's invoice sits **next to the Finance figures of the month it bills** (reconciliation). A tick marks an invoice quantity that equals a figure.
2. **Invoice lines are expanded inline** by default. Today they load behind a "Lines" button.
3. Invoices to **Bexio contacts linked to no Finance client** are listed. Today they are dropped.
4. **Open and unpaid invoices across all months** are listed, oldest due first.

## About the design files
The two `.dc.html` files are **design references built in HTML** (Design Component prototypes; open them in a browser with `support.js` next to them). They are not production code. Recreate them in nexora's own stack: Jinja template + JS shim + `static/js/*.js` + `static/css/*.css` on the `--nx-*` / `nx-sydoc-*` tokens in `static/css/nexora-ui.css`. Turn the inline styles into `nx-bill-*` classes, and reuse the existing classes wherever this README names them. Do not port the inline styles.

- `Sydoc Billing.dc.html`: the new page. Its Tweaks are the sidebar (pinned/collapsed), the invoice lines (expanded/collapsed) and the ticks (on/off).
- `Sydoc Finance.dc.html`: Finance after the change. Its Tweak `version = today` renders the page as it is now (Bexio panel + flat nav), recreated from `finance.html` / `finance.css` / `finance_bexio.js`, for comparison.

All numbers, names, invoices and bookings are **sample data**.

## Fidelity
**High fidelity.** Layout, type, spacing, colours and interactions are final intent, and every value below comes from existing nexora CSS. Dark mode is not designed. Use the existing dark tokens: the band is already `#0b0d12` in dark, and everything below it follows `html.dark`.

---

## Decisions (from the user)
- **The headline month is the invoice month.** `/billing?month=2026-09` lists invoices **dated in September 2026**. These bill **August**, the Finance month `month − INVOICE_MONTH_OFFSET` (`nx_lib/bexio.py`, currently 1).
- **Bexio leaves Finance completely.** There is no link, summary or per-client figure left on Finance.
- **Sidebar:** a **Sydoc** group holds Finance, BPS and Billing.
- **Name:** "Sydoc Billing".
- **Scope:** reconciliation, unlinked contacts, open/unpaid across months, and lines inline.

## Assumptions to confirm
- **Permission:** the page reuses `finance.view`, the gate of today's Bexio routes. A separate `billing.view` would need a migration plus grants (see `docs/design/permissions.md`).
- **Default month:** the previous calendar month, the same rule as Finance. On 1 Oct that is September (invoices for August). October is one click on ›, flagged *Running*.
- **Ticks:** an **exact** match of a line's `amount` against the client's figure values and billed BPS hours. Hours match hours only, and counts match counts only. Cancelled invoices are not matched. No line↔figure mapping exists, so this is a heuristic and is labelled as one.

---

## Changes to existing files

### `templates/finance.html` + friends (remove Bexio)
- Delete the `{{ group_head(_("Invoiced in Bexio")) }}` and the `<section id="fin-bexio">` block.
- Delete the jump-index Bexio item and the separator after it, so the index starts with the internal sections. The first group head ("Internal customers") becomes the first `.nx-fin-group` and gets margin-top 34px through the existing `.nx-fin-group` / `~` rules.
- `templates/js/_finance_js.html`: drop the `bexio: {…}` strings and the `finance_bexio.js` `<script>`.
- `static/css/finance.css`: move the `/* The Bexio invoice panel (#423) */` block (`.nx-fin-sr`, `.nx-fin-bexio*`, `.nx-fin-kpis*`) to `billing.css`, and `.nx-fin-jump__item--bexio` too if it is still needed. Drop `#fin-bexio-refresh` and `.nx-fin-bexio__actions` from the print block.
- `docs/howto/finance.md`: remove "Invoiced in Bexio (#423)" and the Bexio item of the jump index, and point to the new `docs/howto/billing.md`. The CLAUDE.md "Sydoc Finance" paragraph says "A read-only panel shows what was invoiced in Bexio". Change it to point to Billing, and add a one-line **Sydoc Billing** paragraph.

### `templates/_header.html` (sidebar)
Replace the two `nav_items` entries `finance` and `bps` with a collapsible group, built like the Admin/Development groups:
```
<div class="sidebar-nav-group" id="sydocNavGroup" data-active="{{ 'true' if sydoc_active else 'false' }}" data-nx-nav-group="sydoc">
  <button class="sidebar-nav-item sidebar-nav-group-header {{ 'sidebar-nav-item--active' if sydoc_active }}" data-nx-nav-group="sydoc" data-testid="header-nav-sydoc-toggle">
    <i class="fas fa-book sidebar-nav-icon"></i>
    <span class="sidebar-label [flex:1]!">{{ _('Sydoc') }}</span>
    <i class="fas fa-chevron-right sidebar-label sidebar-generali-chevron"></i>
  </button>
  <div class="sidebar-nav-subitems">
    Finance  fa-file-invoice-dollar  url_for('finance')  active_page == 'finance'   (financePagePerm)
    BPS      fa-user-clock           url_for('bps')      active_page == 'bps'       (bpsPagePerm)
    Billing  fa-receipt              url_for('billing')  active_page == 'billing'   (billing perm)
  </div>
</div>
```
- `sydoc_active = active_page in ['finance','bps','billing']`. Render the group if any of the three permissions is held, at the old position (after Global Workitems, before the tenant groups). Keep the old `always: true` behaviour: it shows for single-tenant users too.
- Sub-item labels are short ("Finance", "BPS", "Billing"), because the group header says "Sydoc". Page titles stay "Sydoc Finance" etc.
- Open/close persistence: the generic `data-nx-nav-group` wiring in `static/js/header.js` (localStorage `nexora-nav-sydocNavGroup`; an active group opens itself).
- Active state works as for Admin: the header **and** the sub-item get `sidebar-nav-item--active`. On `body.nx-sydoc` pages the bar is Sydoc orange (existing rule).
- Check the command palette (`_header_js.html`) and the `data-testid`s used by e2e (`header-nav-item-N` indices shift).

### BPS band
No change, but the "Sydoc Finance" link button in its band can stay.

---

## New files
| What | Where |
|---|---|
| Page route `billing` (`/billing?month=YYYY-MM`) | `nx_lib/views/billing.py` (or extend `finance_bexio.py`); register like the other views |
| APIs (see below) | same module; keep `/api/finance/bexio/invoice/<id>` and `/pdf` (or alias them under `/api/billing/…`) |
| Template + shim | `templates/billing.html`, `templates/js/_billing_js.html` (strings on `window.NX_BILLING`) |
| Behaviour | `static/js/billing.js`: grows out of `finance_bexio.js`; uses `NX.apiSafe`, `NXSydoc.initPicker` / `monthCells` / `fmt` |
| Styles | `static/css/billing.css` |
| Docs | `docs/howto/billing.md`, CHANGELOG `[Unreleased]`, CLAUDE.md pointer |
| Tests | move `tests/integration/test_finance_bexio_routes.py` → billing; e2e selectors `finance-bexio-*` → `billing-*` |

`templates/billing.html` follows `finance.html`: `body class="nx-app nx-sydoc"`, `active_page = 'billing'`, `{% import '_sydoc.html' as sydoc with context %}`, and `sydoc.brand(_("Billing"))`, `sydoc.headline(_("Sydoc Billing"), "billing", …, "bill-picker")`, `sydoc.picker_open/year_switch/picker_close`.

**Shared CSS to promote.** Billing reuses three page-local pieces. Move them to `nexora-ui.css` as `nx-sydoc-*` (keep the old names as aliases, or rename in finance/bps):
- `.nx-bps-band__rule`, `.nx-bps-totals*` (bps.css) → band totals row
- `.nx-fin-jump*` (finance.css) → jump index
- `.nx-fin-group*`, `.nx-fin-section`, `.nx-fin-id*` (finance.css) → group heads and ledger rows

---

## Data / API

### `GET /api/billing/month?month=YYYY-MM[&fresh=1]` (month = invoice month)
Built on `bexio.search_invoices(window)` + `reconcile()`, with two changes:
- `reconcile()` keeps the invoices to unlinked contacts and returns them as `others` (with `contact` name). Today they are dropped.
- Each invoice carries its **positions** inline, reusing `normalize_positions()`. Positions are fetched in parallel server-side and cached like the rest (5 min). Fallback: fetch per invoice from the browser, as `toggleLines` does today, but immediately.

Returned shape (extends today's):
```
{ configured, error?, detail?, window:{label,from,to}, billed:{month:'2026-08', label:'August 2026', closed:{atLabel,by}|null},
  readAt:'08:14',
  clients:[{ client, key, contacts:[{name}], state:'invoiced'|'draft'|'missing'|'unlinked',
             invoices:[{ id,nr,title,date,due,status,currency,excl,vat,total,paid,open,contact, bexioUrl, positions:[…] }],
             last?:{ nr, date, status } }],          // last invoice, only for state 'missing'
  others:[{ contact, …invoice }], totals:[{currency,count,excl,total}], drafts, cancelled }
```
- `client.key` is the Finance `Section.client`. The shim also passes `clientSections: {client: [section keys]}` from `nx_lib/finance.SECTIONS`, so the page knows which Finance sections belong to which client.
- `last` is the latest invoice to the client's contacts before the window (one search over the contacts, newest first, limit 1).

### Finance figures (reconciliation)
No new endpoint is needed. `billing.js` calls the existing `/api/finance/section/<key>?month=<billed month>` for every section of every client, in parallel, as `finance.js` does. It reads:
- every `block.figures[]` (`label`, `value`) of the section. A client with several sections (Privera) gets one group per section, titled with `Section.title`.
- from the `bps` section: `bookings.groups[]` → **billed** hours per customer. Privera is split by `Bookings.split` (Posteingang / Invoice / Neuzugänge), as the BPS export does. Label them "Billed hours (BPS)".
- A closed month is served from its snapshot, as on Finance.

### `GET /api/billing/outstanding[?fresh=1]`
All Bexio invoices with status open (8), partial (16) or unpaid (31), **across all months and all contacts**. Use `total_remaining_payments` for the open amount; overdue means `is_valid_to < today`. Sort by due date ascending. Return `client` when the contact is linked, else `contact` + `linked:false`. Totals per currency: CHF outstanding, CHF overdue (count), and other currencies listed apart. As today, nothing is converted.

### Picker month states
Current month: `running`. Past months: `all` (every linked client has a counted invoice) or `missing:n`. Compute this from one Bexio search over the viewed year (cached), or drop it and show the plain month if that is too slow. The Finance picker is unchanged.

---

## Screen: Sydoc Billing

Page shell: unchanged (`.nx-main`, `body.nx-sydoc` → padding-top 36px, orange active bar). Ledger rows use the same grid as Finance: `260px minmax(0,1fr)`, gap 48px, padding 26px 0, bottom border `--nx-border`. Below 1180px they drop to one column, the Finance breakpoint.

### Band: `.nx-sydoc-band.nx-sydoc-band--flush`
- **Row 1:** `sydoc.brand(_("Billing"))`, then a spacer and the actions (`.nx-sydoc-band__actions`):
  - **Sydoc Finance**: `.nx-sydoc-btn.nx-sydoc-btn--link`, `fa-file-invoice-dollar`, href `finance?month=<billed month>`. Shown with `financePagePerm`.
  - **Refresh**: `.nx-sydoc-btn.nx-sydoc-btn--ghost`, `fa-rotate`. Re-calls both APIs with `fresh=1`.
- **Row 2:** `sydoc.headline` shows **September 2026**. Prev/next are inert at the oldest month (the first Finance month + 1) and at the current month.
  - Hint (`.nx-sydoc-hint`): "Invoices dated in {month}, read live from Bexio, each next to the {billed month} figures from Sydoc Finance that it bills. ✓ marks a quantity that equals one of those figures." The second sentence is hidden when ticks are off. The check is `fa-check` 10px `#34d399`.
  - Stats (`.nx-sydoc-stats`): **Bills** = `fa-lock` 11px `#9ca3af` + "August 2026, closed" (or green `.nx-sydoc-dot--live` + "September 2026, open"). **Source** = live dot + "Bexio, read {HH:MM}" (the cache time; failed → `--failed` dot + reason).
- **Totals** (BPS pattern): rule `1px rgba(255,255,255,.08)`, margin `24px -30px 0`. Then a row with margin-top 22px, flex end, gap `16px 48px`:
  - **Invoiced**: eyebrow (10px/700/.1em uppercase `#7c8492`), value 40px/600/−1.6px white tabular "45,174.38" + `small` "CHF" 18px/500 `#7c8492`.
  - Grid (flex wrap, gap `4px 40px`) of eyebrow + 20px/600/−.6px `#f3f4f6` value + `small` 12px/500 `#9ca3af`:
    - **Excl. VAT** "41,789.44" + "CHF"
    - **Invoices** "7" + "1 draft, 1 cancelled". Counted means not draft and not cancelled, in all currencies.
    - **Clients invoiced** "5 of 7" + "2 without an invoice"
    - **Other currencies** "2,035.41" + "EUR, not in the totals". Hidden when there are none; one entry per currency.
- **Jump index** (`.nx-fin-jump`, flush, scrolls sideways): one item per client, in Finance order (tile = `client[:2]`, internal/external tile colours as on Finance, label = the `nav` of the client's first section, else the client). A client that is not invoiced gets a 6px dot `#f59e0b` after its label (`title="Not invoiced"`). Then a separator and two items with the Bexio tile colour (`rgba(52,211,153,.18)` / `#a7f3d0`) and an icon in the tile: **Not linked** (`fa-address-book`, → `#bill-other`) and **Open and unpaid** (`fa-hourglass-half`, → `#bill-open`).

### Groups
`.nx-fin-group` heads: "Internal customers {n}", "External clients {n}" (from `Section.group` of the client's first section), "Other Bexio contacts {n}", and "Open and unpaid {n}" followed by a note `all months, oldest due first` (11px `--nx-fin-quiet`).

### Client row: `section#bill-<key>`
**Identity column:**
- Client: 18px/700/−.02em.
- Bexio contact names joined " · ": 13px/500 `--nx-fin-quiet`.
- State label (`.nx-label`, with dot), margin-top 10px:
  - `invoiced` → green "Invoiced"
  - `draft` → gray "Draft only"
  - `missing` → amber "No invoice in {month}"
  - `unlinked` → gray nodot "No Bexio contact linked"

**Right column: one block per invoice** in date order, 26px apart:
- **Head**: flex, baseline, gap 10px, wraps; padding-bottom 10px; bottom border `--nx-border`. It holds:
  - number: mono 13px/700
  - title: 13px/500 `--nx-fin-quiet`
  - spacer
  - status label: tones as today's `STATUS_TONE` (paid green, open blue, partial amber, draft gray, cancelled gray, unpaid red); label "Partly paid" for partial
  - total: mono 16px/600/−.4px "CHF 9,594.35", in the invoice's own currency
- **Lines**: a table, columns `Text · Quantity · Unit price · Total {cur}`, with Discount only when some line has one.
  - Head cells: 10px/600 uppercase .6px `--nx-fin-quiet`, padding `6px 0`, numeric cells `6px 0 6px 10px`, bottom border `--nx-border`.
  - Rows: text 12.5px; numbers mono 12px, right-aligned, nowrap; unit price `--nx-fin-quiet`; bottom border `--nx-divider`.
  - Quantity: "4,192 Stk" / "21.50 h". When it ticks, a `fa-check` 10px `#047857` sits 6px before the number, `title="Equals the Finance figure {label}"`.
  - Subtotal, discount and text positions keep today's `.nx-fin-bexio__sub` / `__textline` styles.
  - Foot: "Excl. VAT", "VAT {rate} %" (12px `--nx-fin-quiet`), "Total" (12.5px/600).
- **Meta row**: margin-top 6px, padding-top 6px, top border `--nx-divider`, 11.5px `--nx-fin-quiet`, flex wrap, gap `6px 14px`. It holds:
  - text: "Dated 03.09.2026 · due 03.10.2026 · paid 29.09.2026 · to Xpert Consulting AG". "to …" only when the client has more than one contact. A partial payment shows "CHF 4,000.00 paid, 4,158.09 open".
  - an optional note: cancelled → "Cancelled: not in the totals."; draft → "Draft, not issued: not in the totals." (both quiet); foreign currency → "In EUR: not added to the CHF totals." (`#92400e`, 500)
  - spacer, then ghost sm buttons: **Lines / Hide lines** (`fa-list`, only when lines are collapsed by default or the invoice is cancelled), **PDF** (`fa-file-pdf`, the existing PDF route), **Open in Bexio** (`fa-arrow-up-right-from-square`, `bexioUrl`)
- **Cancelled** invoice: number, lines and total in `--nx-fin-quiet`; total struck through; lines collapsed by default.
- **Missing** client: a row with `fa-inbox` and "No invoice to {contacts} is dated in {month}." (13px quiet, bottom border), then 11.5px quiet: "Latest invoice **RE-2026-0371**, dated 05.08.2026, unpaid." The number is mono/600 in ink, and "See Open and unpaid" is a link to `#bill-open` (600 `--nx-sydoc-ink-text`). Use the latest invoice's own status word.

**Finance figures, full width, below the invoices.** The block has `flex-basis:100%` (`grid-column:1/-1` if you keep the grid), margin-top 6px.
- Head: flex, baseline, gap 12px, padding-bottom 6px, bottom border `--nx-border`. It holds the eyebrow "Sydoc Finance · {billed month}" (`.nx-eyebrow`, quiet), a spacer, and the link "Breakdowns in Sydoc Finance →" (11.5px/600 `--nx-sydoc-ink-text`, `fa-arrow-right` 10px, → `finance?month=<billed>#fin-<first section key>`).
- Body: grid `repeat(auto-fill, minmax(200px,1fr))`, gap `0 32px`.
  - A client with titled groups (several sections, or BPS hours split by invoice) gets **one column per group**, titled 11px/600 quiet, margin-top 10px.
  - A client with a single untitled list puts **each figure in its own cell**, so they run side by side.
  - Row: flex, baseline, gap 8px, padding 5px 0, bottom border `--nx-divider`, 12.5px. Label (ellipsis) · value (mono, tabular; hours "21.50 h") · a 12px tick column (`fa-check` 10px `#047857` when a line matches; `title="Billed as: {line text}"`).

### Other Bexio contacts: `section#bill-other`
- Identity:
  - h3 "Not linked"
  - title "To no Finance client"
  - meta "{n} invoices dated in {month}"
  - note (11.5px/1.5 quiet): "Bexio also bills customers nexora has no figures for. These invoices are not in the totals above. A contact that belongs to a client is linked in dbo.FinanceBexioContacts, by migration."
- Right: today's panel table (`.nx-fin-table--wide` › `.nx-fin-matrix` › `.nx-table.nx-fin-bexio__table`). Columns: Contact (600) · Invoice (nr mono 600 + title quiet) · Date · Status · Excl. VAT · Total · PDF. A Total foot row (CHF only).

### Open and unpaid: `section#bill-open`
- Identity:
  - h3 "Outstanding"
  - title "Open, partly paid and unpaid"
  - meta "Every invoice in Bexio with an amount still open, whatever its month · as of {today}"
  - red label "{n} overdue" (all currencies)
- Right, first: the KPI strip (`.nx-kpi-strip.nx-fin-kpis`, value 17px mono) with three tiles:
  - **Outstanding** "CHF 53,369.00" + "10 invoices"
  - **Overdue** "CHF 12,595.50" in `--nx-loss` + "2 invoices"
  - **In EUR** "EUR 3,633.81" + "2 invoices, 1 overdue": one tile per foreign currency, only if present
- Then the table. Columns:
  - Client: linked → client 600 with the contact under it (11px quiet); unlinked → contact 500 with "not linked" under it
  - Invoice
  - Dated
  - Due: the date, plus "{n} days overdue" under it (11px/600 `--nx-loss`)
  - Status
  - Open: mono 600
  - Total: mono, quiet
- Rows are sorted by due date ascending.

### Month picker (`sydoc.picker_open("bill-picker", _("Choose month"), "billing-period-picker")`)
Same grid as Finance. Each cell's status line:
- current month: dot + "Running" (`--running`)
- `missing:n`: `fa-triangle-exclamation` + "{n} missing" (`#b45309`)
- `all`: `fa-check` + "All invoiced" (`#047857`)

Selected: as Finance. Legend: "Every client invoiced" · "Clients without an invoice" · "Still running". A pick navigates to `?month=`.

---

## Interactions & states
- **Navigation:** everything except the line toggles is a URL (`?month=`), as on Finance.
- **Loading:** the band renders from Jinja. Totals and the jump dots show skeletons (`.nx-skel` on ink, as BPS does). Client rows render as server shells, each with a `.nx-fin-skel` until both the Bexio month and its Finance sections have arrived. Ticks are drawn when both sides are in.
- **Errors:**
  - Bexio not configured → today's `plug-circle-xmark` note, in place of the client rows.
  - Bexio error → `.nx-fin-error` under the band, with Retry.
  - A Finance section that fails → its figure group shows the section error inline; the invoice still renders.
  - Outstanding fails → error inside its own section only.
- **Refresh:** bypasses both caches; updates "read HH:MM".
- **Print:** as Finance. Hide the band actions, arrows, jump index and the row buttons; print lines expanded.
- **Motion:** keep `nx-rise` on the band and group heads; nothing else.

## Strings (new msgids, translate de/fr/it)
"Sydoc Billing", "Billing", "Sydoc Billing - nexora", "Bills", "Bexio, read {time}", "{month}, closed", "{month}, open", "Invoices dated in {month}, read live from Bexio, each next to the {billed} figures from Sydoc Finance that it bills.", "✓ marks a quantity that equals one of those figures.", "Clients invoiced", "{n} of {total}", "{n} without an invoice", "Other currencies", "{currency}, not in the totals", "{n} draft, {m} cancelled", "Not linked", "To no Finance client", "Other Bexio contacts", "Open and unpaid", "all months, oldest due first", "Outstanding", "Open, partly paid and unpaid", "Every invoice in Bexio with an amount still open, whatever its month", "as of {date}", "{n} overdue", "{n} days overdue", "Overdue", "In {currency}", "Dated {date}", "due {date}", "paid {date}", "to {contact}", "{paid} paid, {open} open", "Cancelled: not in the totals.", "Draft, not issued: not in the totals.", "In {currency}: not added to the CHF totals.", "No invoice to {contact} is dated in {month}.", "Latest invoice {nr}, dated {date}, {status}.", "See Open and unpaid", "Sydoc Finance · {month}", "Breakdowns in Sydoc Finance", "Billed hours (BPS)", "Equals the Finance figure {label}", "Billed as: {text}", "Hide lines", "VAT {rate} %", "Every client invoiced", "Clients without an invoice", "{n} missing", "All invoiced", "Sydoc" (nav group). Today's `bexio.*` strings move to the Billing shim. Placeholders use `{name}`, not `%(name)s` (see the note in `_finance_js.html`).

## Design tokens
Only existing tokens, no new ones:
- `--nx-sydoc*`, `--nx-gain` `#047857`, `--nx-loss` `#b91c1c`
- label pastels `--nx-l-*`, `--nx-fin-quiet` `#6b7280`, `--nx-border` `#e5e7eb`, `--nx-divider` `#f3f4f6`, `--nx-text` `#1f2937`
- on ink: `#fff` / `#f3f4f6` / `#e5e7eb` / `#d1d5db` / `#9ca3af` / `#7c8492`
- the not-invoiced dot is `#f59e0b` (`.nx-sydoc-dot--running`)
- Type: Inter; numbers `--nx-mono` + tabular-nums.

## Assets
- `assets/sydoc-mark.png` = `static/images/sydoc-mark.png`
- `assets/default-icon.png` = `static/images/default-icon.png` (avatar placeholder)
- Icons are Font Awesome 6.4.2 (already loaded): `fa-book`, `fa-receipt`, `fa-address-book`, `fa-hourglass-half`, `fa-check`, `fa-triangle-exclamation`, `fa-inbox`, `fa-rotate`, `fa-file-pdf`, `fa-arrow-up-right-from-square`, `fa-list`, `fa-lock`, `fa-file-invoice-dollar`, `fa-user-clock`.

## Files in this bundle
- `Sydoc Billing.dc.html`: the new page (approved)
- `Sydoc Finance.dc.html`: Finance after the change; Tweak `version = today` shows the current page
- `support.js`: runtime to open the prototypes
- `assets/`
- `ISSUE.md`: issue text to paste
