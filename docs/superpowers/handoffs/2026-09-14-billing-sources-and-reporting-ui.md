# Handoff — six billing sources live, plus four reporting-UI fixes

**Date:** 2026-09-14 · **Branch:** `docs/handoff-2026-09-14`, cut from
`main` @ `c61047bf` · everything below is **already merged and deployed** —
this handoff is the only thing left to commit · commit-only, the owner pushes.

**Prior handoff:**
[`2026-09-08-report-layouts-execution-complete.md`](2026-09-08-report-layouts-execution-complete.md)

This session ran long and covered two unrelated bodies of work. Nothing is
half-finished. Everything below is merged, deployed and verified on PROD except
`babff28b` (PR #339), which is pushed and waiting on a merge.

## TL;DR

1. **All six of AES Sprint 54's monthly billing workbooks are now nexora
   reporting sources** (`0130`–`0135`), verified figure-by-figure against the
   published Excel files. What is *not* done is anyone from invoicing
   confirming these are the figures they actually bill — that is the whole of
   what keeps #329 open.
2. **`EM_Invoice` keeps changing after a month closes**, values as well as rows.
   Whatever gets invoiced has to be frozen at billing time. This is the single
   most important thing in this document.
3. Four reporting-UI bugs fixed (`c61047bf`), and the owner's verdict was
   *"i like it more but something is still off"* — **unresolved**, parked on
   #336.
4. A latent permissions trap and a never-defined design token were found in
   passing. Both written up.

## What shipped (oldest → newest)

| Commit | What | Issue |
|---|---|---|
| `f4f4a413` | A document nexora cannot load now says so | #321 |
| `aae7c492` | Workitem stage-timeline circles tokenised (were white in dark mode) | #326 |
| `6cad6808` | env-sync stops crying wolf on keys the code defaults | #313 |
| `eb462dbd` | Elektro-Material, Compass, Privera Rechnungseingang, Physische Zustellung | #329 |
| `e9705b33` | Privera Neuzugänge + Posteingang — completes six of six | #329 |
| `dea7e9a7` | Grant the six sources to the `Global Admin` profile | #329 |
| `c61047bf` | Date field, calendar position, range colours, chart hover, wizard flow | #336 |
| `babff28b` | Fireflies over the wizard, rail label alignment, hint spacing | #336 |

PROD is on `c61047b, 2026-09-14`. `babff28b` is on
`fix/336-reporting-wizard-polish` / PR #339 and had not deployed when this was
written.

## The billing sources (#329)

Every one of those monthly workbooks turned out to be a Power Query against a
single SQL object on the statistics server — the server nexora already talks to.
Nothing is imported or copied.

| Source | Object | Agreement with the published workbooks |
|---|---|---|
| `em_invoice` | `dbo.EM_Invoice` | exact on 2 measures in 4 of 6 months, worst gap ~1% |
| `compass_invoice` | `dbo.Compass_Invoice` | exact in 6 of 8 months, 1 document off in the other two |
| `privera_invoice` | `dbo.PriveraInvoice` | 5 of 6 figures exact |
| `privera_nachsendungen` | `01_Privera_Posteingang.dbo.Reporting_P1_Nachsendungen` | exact, all 4 figures |
| `privera_neuzugaenge` | `dbo.v_PriveraNeuzugaenge_…` | 18 of 21 — every closed month |
| `privera_posteingang` | `01_Privera_Posteingang.dbo.Reporting_P1_Dokumente` | exact, cell for cell |

**How the measures were derived, and why it matters:** they were read out of each
workbook's own pivot definition inside the `.xlsx` (`xl/pivotTables/`,
`xl/pivotCache/`), never guessed from the sheet. Each customer's pivot is a
**different shape**, and the differences are load-bearing — they look like
inconsistencies somebody would later tidy up, and tidying any of them changes an
invoice:

- Elektro-Material filters every measure on `Eingang`; the table also holds
  `Nexora` and NULL rows the workbook never counted.
- **Compass filters nothing**, and bills on `UploadDatetime`, not the `DocDate`
  its pivot rows display. Documents uploaded in one month carry document dates
  spread over years.
- Privera splits mail/eBill on `DocSource`, not the workbook's unreproducible
  `FileName` filter.
- Neuzugänge's pivot has a junk fourth field, a summed `JahrExport`, which is
  the year dropped into the values by accident. Deliberately not reproduced.

`tests/unit/test_billing_sources.py` and `test_em_invoice_source.py` pin all of
it, including which columns are deliberately *not* exposed. Each guard was
mutation-checked — put the wrong thing back and the named test fails.

### Two things to carry into use

**`EM_Invoice` is not stable.** Re-running May next year will not return May's
invoice. It is not only rows leaving: April is −3 documents against the workbook
but −190 images, which three vanished documents cannot account for at 2.8 images
each, and March is −7 documents but only −10 images, so retained rows *gained*
images. Values are edited after the month closes, in both directions. The Excel
process had exactly this property and hid it — each workbook froze a copy inside
its pivot cache, which is the only reason a comparison was possible at all.
Compass and Privera do not do this.

**Posteingang has no month grain.** Its `ExportDatetime` is `nvarchar` holding
`dd.MM.yyyy HH:mm:ss`, and the connection runs `us_english`, so asking SQL Server
to read it as a date returns 1 February as 2 January and raises outright past the
12th — both measured against PROD, not assumed. So the column is exposed as a
string and a month is a `contains` filter (`.08.2026`), which reproduces the
published 10,044 exactly. Recovering the grain is one added column on that view:

```sql
TRY_CONVERT(datetime, ExportDatetime, 104) AS ExportDatetime_dt
```

`Reporting_P1_Dokumente` is a **view**, so that is no table change and no
back-fill. Once it exists, adding it to `ColumnsJSON` as a grainable date is the
entire change.

### Permissions — the part that nearly went unnoticed

`0130`–`0135` create each source's permission and grant it to **nobody**.
Enterprise Admin still ends up holding them because that profile holds *every*
permission (136 of 136 on PROD). `Global Admin` does not — it carries a
hand-picked subset — so the six sources deployed correctly and were **invisible
to the one person who needed to check them**. `0136` grants them.

This is not specific to this work: `Global Admin` is also missing `xpert_stats`,
`bucherer_easytax`, `frigemo`, `bps_projects` and most generali sources. Expect
it again next time a source is added.

## The reporting UI (#336)

Four bugs, all found in one sitting going from picking a date range to reading a
chart:

- The range field was **read-only** — every other flatpickr in the app passes
  `allowInput: true`, ten of them, and this one did not.
- Its calendar opened far below the field; it was positioned against `<body>`
  with page coordinates on a page that scrolls thousands of pixels.
- The selected range rendered **light grey in dark mode**. Section 11 of
  `nexora-ui.css` covered single-date pickers and never `.inRange`. Three pieces
  had to move together: the band, the box-shadow flatpickr uses to fill the
  *seams between cells*, and its own `.flatpickr-day.today.inRange` — three
  classes, which outranks a two-class override. That last one is why today's
  date stayed a white block in the middle of an otherwise-fixed range.
- The chart only responded with the cursor **exactly** on a data point.

Plus the wizard: Continue revealed the next question below the fold without
scrolling, so it read as doing nothing; and the group caption sat **2px** above
the chips it labels.

**`--nx-on-accent` was referenced but never defined.** `nexora-ui.css` used
`var(--nx-on-accent, #fff)` for the permission-override badge and nothing ever
declared the token, so it always fell back to white — fine on light mode's dark
accents, wrong on dark mode's pale ones. Now declared per theme. This changes the
badge on `/admin/permissions` as well as the calendar.

### The second round (`babff28b`, PR #339)

The owner's *"something is still off"* turned out to be three more things, and
all three are worth knowing because each was a leftover rather than a taste
call:

- **The firefly backdrop painted over the wizard.** The dots are held behind
  the page by promoting `<main>` — and Reporting is the one page whose content
  is not all inside `<main>`. Fixed by giving `.reporting-shell`
  `position: relative` and **deliberately no `z-index`**: enough to paint above
  the dots, while leaving the fixed panels inside the shell free to escape to
  the root. Give it a z-index and `#rpChatPanel` gets trapped below the sidebar.
  The obvious alternative — `z-index: -1` on the dots — **deletes the effect**,
  because html and body both carry the page background. Measured with all 16
  dots forced visible; none rendered.
- **The rail labels sat 2.5px below their numbers.** `.rs-rail-title` still
  carried `padding-top: 4px` from the original *vertical* rail. The Console
  reuses that markup horizontally, where the chip centres dot and label against
  each other, so the padding pushed the label down inside a centred box.
- **`.reporting-simple-hint` had no rule at all**, so every "Pick one or more…"
  line inherited 16px primary-colour body text with zero margin — louder than
  the answers it explains, and touching them.

`tests/unit/test_reporting_wizard_styles.py` pins all three plus the two wrong
turns, mutation-checked.

**One reversal to review:** the wizard step headings dropped the uppercase
tracked-caption treatment the console redesign gave them ("Task 7" in
`reporting.css`). Reasoning is in the rule's comment. If the consistency argument
wins, it is one rule to revert.

**Two traps worth knowing for anyone touching this again:**

1. **Simple and Advanced own separate Chart.js modules.** Simple deliberately
   does not call `ReportingViz.mountChart`. I patched one and a test showed the
   old config still live — both need it.
2. **The preview pane scales the page**, so `getBoundingClientRect()` misreports
   positions by ~20px. It sent me chasing a phantom "calendar overlaps the
   input" until I switched to layout pixels (`offsetTop`/`offsetHeight`). Verify
   CSS positioning that way, not from a screenshot.

## Next steps, in order

1. **Get the billed figures confirmed** by whoever does the invoicing. Open a
   real month next to the workbook and walk the measures. This is the only thing
   between "the numbers match" and "bill from it", and it is what keeps #329
   open.
2. **#336 — closed.** The *"something is still off"* was pinned down and
   fixed in `babff28b` (PR #339). Nothing outstanding.
3. **#330 — Privera Mailbestellungen.** Recommendation is to *leave it manual*:
   it is one count a month (465 for August) and the manual process is correct.
   The only case for building it is that the branch is sitting in every subject
   line (`Physische Nachsendung <no.> (<Branch>, <CODE>)`, parses for 464 of 465
   rows across 14 branches) and gets thrown away, while every other Privera
   report splits by branch. Ask Privera whether they want that; if not, close it.
4. **#332 — reporting source grants.** Three items, and only the first is
   blocked. **None of them has shipped** — as of this handoff
   `scripts/perm-audit.py` contains neither check. Grep it before
   assuming otherwise; an earlier draft of this document implied they had
   landed and a later session nearly closed the issue on that reading.
   1. *Blocked:* why `Sydoc User` holds the MediaMarkt source without
      `reporting.view`. It looks *intended but unfinished* rather than
      accidental, so #333 (which dropped it) was closed unmerged. Needs
      whoever granted it.
   2. *Unwritten:* two `scripts/perm-audit.py` checks — a profile holding a
      `reporting.source.*` without `reporting.view`, and a profile with an
      `OrganizationCode` holding another customer's source.
   3. *Unwritten:* the rule for when a `table` source may be granted to a
      customer profile. The `table` provider applies no row scoping, so the
      source permission is the entire gate.
5. **#323 — Ben's Eddard bug.** Diagnosed, untouched: `fireCaption()` sits at
   `static/js/reporting_simple.js:538`, after the layout branch's `return` at
   `:518`, so it never runs for a report with a saved layout. `setAskEddard()`
   is at `:489`, before the branch, which is exactly why "Ask Eddard" is the one
   that works.
6. **#267 — three environments.** Parked until the Cloudflare Tunnel cutover;
   on ngrok every extra hostname costs money. Note the deploy **stops the shared
   tunnel service**, so a naive dev deploy would take production down on every
   branch push.

## Gotchas and notes

- **`--nx-on-accent` now exists.** Anything that was relying on the `#fff`
  fallback in dark mode will look different — deliberately.
- **Seven deploys this session**, all approved. Each merge to `main` is a ~34s
  IIS restart; always ask about timing.
- **Migration numbering:** `0128` is used twice in the repo
  (`0128_generali_renamed_objects.sql` and `0128_seed_xpert_stats_source.sql`) —
  the exact collision the "claim the NNNN first" rule exists to prevent. Next
  free number is `0137`.
- The environment traps still apply: `jq` is not on PATH (use `gh -q`), and
  `python` is the Store stub (use `.venv/Scripts`).

## How to verify

```bash
# the six sources, live
start https://nexora.sydoc.ch/nexora/reporting     # New report → scroll to the bottom groups

# two spot figures that should match the workbooks exactly
#   Compass, May 2026                      -> 9,185
#   Posteingang, contains ".08.2026"       -> 10,044

# locally
.venv\Scripts\python.exe -m pytest tests/unit -q   # 1848 passed, 36 skipped
```

Nothing is currently failing.

## Untracked / left for the owner

Nothing. The working tree is clean apart from this handoff, and no scratch files
were left in the repo.
