# Sydoc Controlling: monthly margin per client stream (third Sydoc page)

Replaces the hand-filled controlling workbook. Per client stream and month: BPS hours × rate = cost, against what was invoiced in Bexio (excl. VAT) = margin. Global Admin only. Same band, picker and ledger as Sydoc Finance and Sydoc BPS.

**Design:** `docs/design/design_handoff_sydoc_controlling/` — option **1a** in `Sydoc Controlling.dc.html`. The spec is in `README.md`.

## Scope
- [ ] Page, route, sidebar item (`fa-scale-balanced`), permission `controlling.view` (Global Admin).
- [ ] Ink band via `_sydoc.html`: Excel / Print / Rates actions, month headline + picker (closed / open / running), Status + Rate stats, jump index (Summary · Clients · Hours by task · Volumes · Trend).
- [ ] Month summary strip: hours, cost, invoiced excl. VAT, margin CHF + %, documents, each with a good/bad-coloured delta.
- [ ] Margin by client: hours, cost, invoiced excl./incl. VAT, diverging margin bar, margin %, Δ vs previous month, total row (issued CHF invoices only), flags (no invoice / draft / EUR / not linked / not invoiced yet), unassigned-invoice warning rows.
- [ ] Per-client blocks (collapsed summary, one open at a time): Aufwendungen nach Tätigkeit, Debitor-Positionen (Bexio lines, status, PDF), Differenz, unit figures; Finance's drift note in closed months.
- [ ] Hours by task: task × stream heatmap matrix, totals, FTE row.
- [ ] Document volumes per stream.
- [ ] Trend since Jan 2025: total margin + hours + documents on shared columns, small multiples per stream, synced hover.
- [ ] Rates drawer: default rate history, per-stream overrides, add/edit, `controlling.rates.edit`.
- [ ] States: incomplete source (Privera Jan–Oct 2025), closed month snapshot + live Bexio drift, loading, per-section errors, empty month, dark mode, phone width, print.
- [ ] Migrations: permissions, `ControllingRates`, `ControllingBexioProjects`, controlling snapshot at month close.
- [ ] Token `--nx-sydoc-quiet`; i18n; unit, integration and e2e tests; `docs/howto/controlling.md`.

## Open points
1. Is a controlling month closed with Finance's close (assumed) or separately?
2. Hours per FTE: 176 h assumed.
3. Hours delta coloured like cost (up = red) — confirm.
