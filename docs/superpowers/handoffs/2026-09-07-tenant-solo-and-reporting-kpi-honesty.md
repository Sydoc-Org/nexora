# Handoff — a tenant's own users stop seeing it named, and the reporting KPI tiles stop lying

**Date:** 2026-09-07 · **Branch:** `refactor/255-admin-nav-tenancy-labels` (main checkout
`C:\dev\nexora`, no worktrees) · **94 commits ahead of `origin/main`, nothing pushed** ·
commit-only — the owner pushes and opens the PR.

**Prior handoff:** [`2026-09-07-one-branch-238-254-merged.md`](2026-09-07-one-branch-238-254-merged.md)
(same date — `/reset-session` may pick either; that one carries a forward-pointer banner to this file).

## This session's commits (oldest → newest)

| Commit | What |
|---|---|
| `d3802931` | **not this session** — a *parallel* Claude session's `chore(sql)` dump of the `0106` trigger. It swept this session's in-progress `CHANGELOG.md` edit into itself (see Gotchas) |
| `4d6b755e` | #255: `tenant_solo` — a tenant's own users never see it named (sidebar label + both page headings) |
| `2a6da27b` | reporting: the KPI tiles say what they compute (Buckets/Avg/headline caption/NULL exclusion) |

## TL;DR

1. **Normal users now see a pre-tenant-kernel UI.** A user who belongs to exactly one tenant and
   holds no grant on another gets no tenant label in the sidebar and plain `Dashboard` / `Workitems`
   headings. Verified in the browser for PDBS, Privera and ISS/Generali; staff keep every name.
2. **The reporting KPI band was mislabelled, not broken.** The data was always right. Buckets
   counted rows (112 under "periods in the range" where there were 3), Avg claimed an arithmetic it
   never performed, the headline `AVG()` was captioned as a sum, and NULL-period rows the chart
   drops were silently counted. All four fixed in Simple **and** the Advanced mirror.
3. **The branch is PR-ready.** Full gate green apart from the two known order-dependent rate-limit
   tests. A PROD permission-migration audit found no orphaned grants (details below).
4. **Merge GRuoss's three PRs first** — #262 and #276 merge clean into this branch, #261 conflicts
   only in `templates/_header.html`. No SQL migrations in any of them.

## What shipped

### `4d6b755e` — #255 a tenant's own users never see it named

| File | Change |
|---|---|
| `nx_lib/hooks.py` | `_inject_tenant_nav()` returns a third key, `tenant_solo`: true when the user's org belongs to a tenant, that is the only tenant in their nav, and it is their own |
| `templates/_header.html` | the flat-sidebar branch and the `single_tenant` set both read `tenant_solo` instead of spelling the condition out twice; the `sidebar-section-label` div with the tenant name is **deleted** |
| `templates/dashboard.html` | `<Tenant> Dashboard` → plain `Dashboard` when `tenant_solo` |
| `templates/workitems_overview.html` | `<Tenant> Workitems` → plain `Workitems` when `tenant_solo`; the "Workitems of this tenant's processes only" subtitle drops too (a scope they can never leave needs no explaining) |
| `tests/unit/test_hooks.py` | the two `_inject_tenant_nav` tests pin the exact dict, so both gained `tenant_solo` |
| `tests/integration/test_tenant_routes.py` | `test_header_renders_a_single_tenant_flat_for_its_members` now asserts the label testid is **absent** |
| `docs/howto/white-label.md` | new "A tenant's own users never see it named" paragraph — adding a name back to a page a solo member can reach is a regression |
| `messages.pot`, `translations/{de,fr,it}` | one new msgid, `"Workitems"` (stays "Workitems" in all three, matching `"Global Workitems"`) |

The `CHANGELOG.md` entry for this lives in `d3802931`, not `4d6b755e` — see Gotchas.

### `2a6da27b` — reporting KPI tiles

Symptom on `Extraction correct % by per month / Field` (4 periods × 28 fields = 112 rows, one
period NULL):

| Tile | Before | After |
|---|---|---|
| headline | `TOTAL · 34.501 · sum over the period` | `OVERALL · 34.501 · over every matching row` |
| Buckets | `112 · periods in the range` | `3 · periods in the range` |
| Avg | `AVG PER BUCKET · 54.029 · total ÷ buckets` | `AVG PER ROW · 55.416 · mean of 84 values` |
| Peak | `100 · **null** · doccurrency` | `100 · 2025-09-01 · crdno` |

| File | Change |
|---|---|
| `static/js/reporting_simple_result.js` | `computeKpiBand`: filters NULL-leading-dimension rows into `kept`, counts distinct leading-dim values into `buckets`, keeps the old row count as `cells`, `avg = total/cells`. New `metricAggs(def)` (per-metric aggregation, mirroring `metricTotalModes`). `measureTotals` carries `agg` and applies the same NULL filter to its fallback sum. Renderer switches caption (`kpiTotal`/`kpiOverall`), sub-line (`kpiSumSub`/`kpiExactSub`) and the avg title+sub on `cells === buckets` |
| `static/js/reporting_advanced.js` | the Advanced grid's `computeKpiBand` mirror had the same `buckets = rows.length` bug; same fix, plus the avg-title switch. Its tiles carry no sub-lines, so only the title needed a second string |
| `templates/js/_reporting_simple_js.html` | new I18N: `kpiOverall`, `kpiExactSub`, `kpiAvgCell`, `kpiAvgCellSub` |
| `templates/js/_reporting_js.html` | new I18N: `kpiAvgCell` |
| `templates/_reporting_help.html` | three new tips (Overall vs Total, Buckets counts periods, undated rows are excluded) — the `reporting-help-sync` hook requires this alongside a user-visible reporting change |
| `tests/unit/test_reporting_kpi_band.py` | **new**, 10 tests |
| `docs/howto/reporting.md` | two new bullets under "Distribution stats need a distribution"; "Avg-per-bucket chip" → "Avg chip" |
| `docs/howto/reporting-guide.md` | end-user guide: Overall cards, Buckets-counts-periods, undated rows left out |
| `CHANGELOG.md` | entry under `[Unreleased]` → Fixed |
| `messages.pot`, `translations/{de,fr,it}` | 7 new msgids, all three locales translated non-fuzzy |

## Next steps (ordered)

1. **Merge GRuoss's three open PRs into `main` first**, then merge `main` into this branch. Verified
   read-only with `git merge-tree` against `HEAD`:
   - **#262** `fix/227-prune-active-sessions` — clean
   - **#276** `fix/246-reporting-schema-i18n-fallbacks` — clean
   - **#261** `fix/243-accent-verify-2fa` — **conflicts in `templates/_header.html` only**
     (`CHANGELOG.md` auto-merges). #261 lifts a ~160-line UI-prefs pre-paint block out of
     `_header.html` into a new `_ui_prefs_prepaint.html`; this branch's edits are in the tenant-nav
     section further down, so the conflict is positional, not semantic.

   None of the three contains a SQL migration, so nothing can disturb the `0086`–`0115` chain.
2. **Push this branch and open ONE PR** to `main`, linking #238, #254, #255, #256, #257.
3. **PROD deploy, off-hours** (D6): migrations `0086`–`0115` apply before the app pool stops; the old
   build 403s during the window. `scripts/env-sync.py` by habit — no new env keys.
4. After deploy: close #238 and #254; eyeball `/admin/permissions` against `var/screenshots/238_*.png`.
5. Carried over, untouched: `compassUser` → CMPS, #256 entity/field editors, tenant delete leaving
   `tenant.<code>.*` rows, INT oddities (Privera logo 404 and ISS org showing the `nexora` brand —
   both pre-existing, neither touched here), and the What's New card for the #238 grid still sitting
   in the 3.2.4 block (move it when cutting the next release).

## Gotchas & notes

- **A parallel Claude session is committing on this same branch.** It landed `d3802931` at 11:57 and
  its pre-commit stash swept this session's `CHANGELOG.md` edit for #255 into that commit — content
  is on the branch, just attributed to the wrong commit. It also made three already-fixed tests
  flap mid-gate (they re-verified green individually). **Check `git log -5` and settle that session
  before pushing.** Commit with an explicit pathspec, never `git add -A`.
- **`buckets` semantics changed** and `kpi.buckets` also feeds the avg delta-chip guard
  (`kpi.buckets === priorKpi.buckets` in `kpiBandHtml`). That guard now compares *period* counts,
  which is what its comment always described. `docs/howto/reporting.md` records this.
- **`measureTotals`' fallback sum must keep the same NULL filter as `computeKpiBand`** or
  `seriesIsHeadline` stops matching and the sparkline + delta chip vanish for every report with
  undated rows. `test_measure_totals_fallback_agrees_with_the_band` pins it.
- **The 34.501 was never wrong.** It is `AVG(CorrectPct)` over 29,756 underlying rows, confirmed to
  five decimals against SQL. Only its caption was.
- **Stale `NEXORA_TEST` fakes failures.** 12 reporting-route and 6 dashboard/workitems failures this
  session were pure stale-DB; all green after `scripts/test_db_reset.py`. Run the reset **before**
  believing any failure. The shared applock also made a run wait 62 s for a colleague — wait, don't
  kill. `tests/unit/test_reporting_kpi_band.py` touches no DB, so `NEXORA_TEST_LOCK_SKIP=1` is safe
  for it alone.
- **PROD permission-migration audit (read-only, done this session).** 142 live PROD codes; the 37
  absent from `0088`'s literal map are all covered by pattern in `0086` (`invoices.%`,
  `kundenmagazin.%`, `admin.assign.user.accessprofile.%` deleted) and `0087` (the three
  per-process families collapsed into `process.<client>.<name>.view`). Grants ride on
  `PermissionID`, so a rename drops nothing. `0087`'s collapse widens exactly **2** profile×process
  pairs once `0086` removes the 55 deny rows (`enterpriseAdmin` and `pdbsUser` gain reporting scope
  on `sydoc.05_PDBS`) — and it is **inert**: `pdbsUser` holds no `reporting.*` code at all.
- **`CLAUDE.md`'s DB engine names are stale** — it documents `engineNexoraDB` etc., but `nx_lib/db.py`
  exports `engine_nexora_db`, `engine_octo_db`, `engine_statistics_db`, `engine_generali_db`. Also
  `dbo.AccessProfiles`/`Users.Id` don't exist; the real tables are `dbo.AccessProfile` (`AccessID`,
  `Name`) and `dbo.Users` (`userID`, `username`, `organizationCode`). Worth a docs fix.
- **Bash-tool heredocs mangle long scripts** — hit it again this session. Write the Python to
  `var/*.py` with the Write tool and run the file.
- Screenshot evidence (gitignored): `var/screenshots/255_pdbs_sidebar_no_tenant_label.png`,
  `255_pdbs_dashboard_plain.png`, `255_pdbs_workitems_plain.png`, `255_privera_dashboard.png`,
  `255_generali_iss_dashboard.png`, `255_staff_tenant_dashboard_named.png`,
  `reporting_check_result.png` (before), `reporting_kpi_fixed.png` (after).

## Untracked / left for owner

- **`docs/nexora-architecture.drawio` is MODIFIED and uncommitted**, plus untracked
  `docs/nx-architecture.drawio`, `docs/architecture/nx-architecture.png`,
  `docs/.$nexora-architecture.drawio.bkp`, `docs/.$nx-architecture.drawio.bkp`. These are the
  owner's / the parallel session's diagram work — **deliberately not committed** by this session.
  Note `docs/architecture/` is a new top-level-ish directory: if it should not reach PROD, add it to
  the robocopy exclude list in `deploy.yml` (`/XD`).

## How to verify

```powershell
# ALWAYS reset first -- a stale NEXORA_TEST invents failures (see Gotchas)
$env:ENVIRONMENT = "TEST"; .venv\Scripts\python scripts\test_db_reset.py

# this session's two changes
.venv\Scripts\python -m pytest tests/unit/test_reporting_kpi_band.py tests/unit/test_hooks.py `
  tests/integration/test_tenant_routes.py tests/unit/test_translations.py -q -p no:cacheprovider --no-cov

# everything reporting/template-shaped (804 passed at 2a6da27b)
.venv\Scripts\python -m pytest tests/unit tests/integration -q -p no:cacheprovider --no-cov `
  -k "reporting or kpi or template"

# full tier (~9 min). Expect ONLY the two known order-dependent rate-limit tests to fail:
#   test_rate_limit_429_for_unauthenticated_requests, test_verify_2fa_rate_limit_eventually_429
.venv\Scripts\python -m pytest tests/unit tests/integration -q -p no:cacheprovider

# migrations up to date on INT (0086-0115); next free number is 0116
.venv\Scripts\python scripts\db-migrate.py --env INT --db NexoraDB --dry-run

# live -- restart first, Jinja templates are cached for the process lifetime
bin\nx.ps1 -r --port:8000
#   /dev/login/demo.user      -> PDBS: flat sidebar, no tenant label, plain "Dashboard"/"Workitems"
#   /dev/login/germaine.heldner, /dev/login/robin.krieg -> same, Privera and ISS/Generali
#   /dev/login/ben.streich    -> staff keep "Mobscn Dashboard" and the Global entries
#   /reporting -> open "Extraction correct % by per month / Field":
#                 OVERALL 34.501 / BUCKETS 3 / AVG PER ROW 55.416 / PEAK 100 at 2025-09-01 · crdno
```

## Resuming in a fresh session

Run `/reset-session docs/superpowers/handoffs/2026-09-07-tenant-solo-and-reporting-kpi-honesty.md`
— pass the path explicitly, because
[`2026-09-07-one-branch-238-254-merged.md`](2026-09-07-one-branch-238-254-merged.md) shares today's
date and a bare `/reset-session` may pick that one instead.

Nothing is red. The branch waits on GRuoss's three PRs, then the owner's push and one PR.
