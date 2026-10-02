## Sydoc Billing: move Bexio off Finance onto its own page

The Bexio invoice panel (#423) leaves `/finance` and becomes **Sydoc Billing** (`/billing?month=YYYY-MM`), the third page of Sydoc's books next to Finance and BPS. Design and spec: `docs/design/design_handoff_sydoc_billing/` (README + `Sydoc Billing.dc.html`).

**Scope**
- [ ] `/billing` page (`templates/billing.html`, `_billing_js.html`, `static/js/billing.js`, `static/css/billing.css`) on the shared Sydoc band, headline and picker
- [ ] Headline month = **invoice month**; it bills `month − INVOICE_MONTH_OFFSET`. Default = previous calendar month
- [ ] Per client: invoices with **lines inline**, next to the **Finance figures of the billed month** (incl. billed BPS hours); ✓ when a quantity equals a figure
- [ ] **Other Bexio contacts**: invoices in the month to contacts no client is linked to (`reconcile()` stops dropping them)
- [ ] **Open and unpaid, all months**: open / partly paid / unpaid invoices, oldest due first, CHF outstanding + overdue, other currencies apart
- [ ] APIs: `GET /api/billing/month`, `GET /api/billing/outstanding` (keep the invoice + PDF routes)
- [ ] Remove the Bexio panel, its group head, jump item, strings, script and CSS from Finance
- [ ] Sidebar: **Sydoc** group (`fa-book`) with Finance, BPS, Billing (`fa-receipt`); generic `data-nx-nav-group` wiring
- [ ] Translations de/fr/it, `docs/howto/billing.md`, `docs/howto/finance.md`, CLAUDE.md, CHANGELOG
- [ ] Tests: move `test_finance_bexio_routes.py`, update e2e selectors (`finance-bexio-*`, sidebar nav indices)

**Open questions**
- Own permission `billing.view`, or keep `finance.view`?
- Picker month states (all invoiced / n missing) need a yearly Bexio search. Keep it or drop it?
