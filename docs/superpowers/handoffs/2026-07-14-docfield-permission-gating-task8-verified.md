> **Addendum (same day, later):** Owner action 2 is also done now — see the bottom of this
> file. Both owner-only data actions from the plan are complete; only permission grants +
> PROD rollout + push remain.

# Handoff — Permission-gated doc-fields (Validation User) — ALL 8 TASKS DONE, live-verified

**Date:** 2026-07-14 (morning) · **Branch:** `feature/2.5.64` · **commit-only (remote session — owner pushes)** · no plan worktree
**Prior handoff:** `2026-07-13-docfield-permission-gating-execution-complete.md` (same plan, prior day — 7/8 tasks, Task 8 blocked on VPN/DB access + a missing owner action)
**Plan:** `docs/superpowers/plans/2026-07-13-docfield-permission-gating.md` (no further changes needed)

## TL;DR

- **This plan is now fully done.** Task 8 (live INT browser verification), the only item
  left open from yesterday, is complete. **No code changes this session** — verification
  only, working tree clean throughout.
- **DB/VPN connectivity came back** (`nx --doctor`: 29 ok, 1 warn, 0 fail — every database
  and Octopus reachable, vs. 8 fail yesterday). Re-ran the full previously-blocked test
  suite first: **66/66 pass genuinely** (`tests/integration/test_workitems_routes.py`),
  including all 14 doc-field sensitivity tests that could only be "logically verified" via
  code-reading + manual scripts yesterday.
- **The owner had already mapped the field** before this session resumed:
  `col_validationuser = 'ValUserA'` for `compass.01_Invoice_SAP` / `default` (StatisticsDB,
  not MS02) — Owner action 1 from the plan, done.
- **The Critical fix from yesterday's final review (`api_workitems_page_init` gating) is
  now proven live, end-to-end, with a real screenshot**: the permissioned user's actual
  rendered doc-field dropdown shows "Validation User" between "Target System Filename" and
  "Vat Amount"; the unpermissioned user's identical dropdown skips straight past — same
  process, same list, only the permission differs.
- **Values API and CSV/detail-panel surfaces returned empty for both users** — verified
  this is real-data absence, not a bug (see Gotchas). *(Update: Owner action 2 was completed
  later the same day — see the Addendum at the bottom. The panel/CSV gates still have
  nothing live to observe only because no document has been through Octo validation yet,
  not because anything is unmapped.)*

## What was done this session (no commits — verification only)

1. Confirmed DB/VPN connectivity restored via `nx --doctor`.
2. Re-ran `tests/integration/test_workitems_routes.py` in full: **66/66 pass**. Ran the
   14-test `-k "docfield or config_fields or strip_sensitive or strip_export"` slice
   specifically: all pass, converting every "logically sound but unrun" test from
   yesterday's session into a genuine pytest GREEN.
3. Queried `SearchConfig` directly (`ENVIRONMENT=INT` + `nx_lib.db.engine_nexora_db`) —
   confirmed the owner's mapping: `col_validationuser = 'ValUserA'`,
   `ProcessName = 'compass.01_Invoice_SAP'`, `ClientCode = 'default'`.
4. Created a throwaway INT user `test.task8.noperm` (direct SQL insert into `Users`,
   `AccessID` = `compassUser`'s — has `workitems.filter.documentfields` +
   `workitems.filter.process.compass.01_Invoice_SAP` + `workitems.details.view.fields`, but
   NOT the sensitive perm). Used `ben.streich` (enterpriseAdmin, already has the sensitive
   perm via migration `0035`'s auto-grant) as the permissioned counterpart. **Deleted the
   throwaway user after testing — confirmed 0 remaining rows, no orphan.**
5. Restarted the dev server (`nx -r`), then drove the real running app as both users via a
   standalone Playwright script (`claude-in-chrome` extension unavailable this session too
   — same substitution the pdbsuser plan's Task 7 used). Checked all 4 plan checklist items
   for both users; see results below.
6. 11 screenshots in `var/screenshots/` (gitignored), sent to the user via `SendUserFile`.

## Results (Task 8 checklist, plan Phase 6)

| Check | No-perm user | Perm user (ben.streich) | Verdict |
|---|---|---|---|
| **Dropdown** | "Validation User" absent from the real rendered list | Present, between "Target System Filename" and "Vat Amount" | **PASS — proven live with a screenshot** |
| **Values API** (`/api/docfield_values?field=validationuser&process=compass.01_Invoice_SAP`) | `200 []` | `200 []` | Both empty, but for an unrelated reason — see Gotchas. Not a defect. |
| **Detail panel** (`/api/get_media_info/<wid>`) | No Validation User field present | No Validation User field present (same workitem, same result) | No live Octo-extracted data to gate yet — see Gotchas. Code-path already verified correct in Tasks 5 + final review. |
| **CSV export** (`include=fields`) | No Validation User column | No Validation User column | Same as detail panel — nothing to strip on this data yet, not a defect. |

**The dropdown result is the one that matters most**: it's the surface the Critical
whole-branch-review finding (`api_workitems_page_init` being the real, previously-ungated
route) was about, and it's now directly, visually confirmed working correctly in the live
app.

## Gotchas & notes (READ)

- **Values API `[]` for both users is NOT the sensitivity gate — it's the pre-existing
  `SuggestionTimeFilter`.** Queried the real `StatisticsDB.dbo.Compass_Invoice.ValUserA`
  column directly: 86 non-null rows, 9 distinct values (e.g. `DOM\BES`), but the
  `SearchConfig.SuggestionTimeFilter` for this row is `ImportDate >
  DATEADD(day,-7,GETDATE())` and all the real data is older than 7 days. This filter
  applies identically to every doc-field's autocomplete, not something this plan touched.
  The sensitivity GATE's correctness (that a permissionless caller short-circuits *before*
  the query even runs) was already proven at the code/test level in Task 4 — this live
  check just couldn't additionally distinguish "gate blocked it" from "time filter would
  have anyway" for the *permissioned* case, since both paths landed on empty.
- **Detail panel / CSV showed nothing because Octo doesn't currently extract a "Validation
  User" field for `compass.01_Invoice_SAP` at all** (checked the one tested workitem,
  18411, and its real extracted `fields`: `Client, CrdName, CrdNo, DocBarcode,
  DocCurrency, DocDate, DocSource, DocType, GrossAmount, InvoiceNR, NetAmount,
  TargetSystemFileName, VatAmount, emailfromaddress` — no Validation User-like key). This
  is expected: the doc-field SEARCH mechanism (`col_validationuser` → `ValUserA` in
  StatisticsDB, which the owner just mapped) and the Octo EXTRACTION mechanism (what
  `get_extensions_urls_fields` returns per document) are two separate systems by design
  (D5 in the plan). **Owner action 2 — confirm the Octo extraction target-key normalizes to
  `validationuser`/a seeded label, or add the spelling — is still outstanding** and is
  exactly why. Until that's done, the panel/CSV gates are correct-by-code (verified in
  Tasks 5, 6, and the final whole-branch review) but have nothing live to observably strip.
  Not a regression, not new work — the plan flagged this dependency from the start.
- **Yet another concurrent session appeared on this branch overnight**: commit `66ca845`
  "docs(handoff): queue reporting drill-through execution" landed, and
  `var/handoff-pending` now points to
  `docs/superpowers/handoffs/2026-07-14-execute-reporting-drill-through.md` — an unrelated,
  still-pending plan. **This handoff deliberately does NOT overwrite that flag** (this
  plan is fully done, nothing to resume; overwriting would break the other session's
  resume path). If you're picking up fresh and expected to land here instead, target this
  file explicitly: `/reset-session
  docs/superpowers/handoffs/2026-07-14-docfield-permission-gating-task8-verified.md`.
- **Screenshots**: `var/screenshots/docfield-task8-*.png` (11 files, gitignored). The key
  one is `docfield-task8-perm-dropdown-scrolled-to-validationuser.png` (shows "Validation
  User" live in the real dropdown) alongside
  `docfield-task8-noperm-docfield-dropdown-open.png` (shows it absent from the same list).
- **No app code was touched this session.** All git state is exactly as the prior handoff
  (`ee524d7`) left it, plus this handoff commit.

## Owner actions still pending (unchanged from yesterday's handoff, minus #1 which is done)

1. ~~Map the field to its real source column~~ **DONE** (owner did this before this session:
   `col_validationuser = 'ValUserA'` on `compass.01_Invoice_SAP`/`default`).
2. ~~Confirm/wire the Octo extraction name~~ **DONE** (migration `0036`, same day — see
   Addendum at the bottom).
3. **Grant the permission** to the right non-admin profiles via the admin UI (currently
   only `enterpriseAdmin`/`globalAdmin` have it, via `0035`'s auto-grant).
4. **PROD rollout** — `0035` AND `0036` reach PROD automatically on the next deploy to
   `main`, or immediately via `python scripts/db-migrate.py --env PROD`.
5. **Review + push `feature/2.5.64`** (full pre-push gate incl. Playwright e2e).

## Untracked / left for owner

- Working tree clean except the user's own unrelated `package.json`/`package-lock.json`/
  `node_modules` (confirmed intentional in the prior session, not this plan's concern).
- The throwaway test user (`test.task8.noperm`) was created and fully cleaned up within
  this session — nothing left behind in `dbo.Users`.

## How to verify

```powershell
# From C:\dev\nexora (feature/2.5.64):
nx --doctor                              # confirms DB/VPN state at time of reading
.venv\Scripts\python -m pytest tests/integration/test_workitems_routes.py -q   # 66 passed
```

## Resuming in a fresh session

Nothing to resume for this plan — it's complete. If the `var/handoff-pending` flag points
elsewhere (it currently points to the unrelated `reporting-drill-through` plan), that's
correct; this file is for the historical record, not an active resume point.

## Addendum: Owner action 2 done too (same day, migration 0036)

The user supplied the missing piece right after this handoff was written: Octo's raw
extraction index field is named `ValUser`, and it needed a row in `dbo.IndexFieldMappings`
— a **separate table** from `SearchConfig`/`Search_Field_Labels`, consumed by
`nx_lib/octo.py`'s `get_index_field_mappings()`/`get_extensions_urls_fields()` to translate
Octo's raw `IndexFields[].Name` into the key that lands in the `fields` dict the detail
panel/CSV/sensitivity-strip all key off. Checked the table first: no existing `ValUser` row;
established convention is PascalCase `TargetKey` (`CrdName`, `DocBarcode`,
`TargetSystemFileName`). Added migration `0036`
(`sql/_migrations/NexoraDB/0036_index_field_mapping_validation_user.sql`):
`INSERT INTO IndexFieldMappings (SourceFieldName, TargetKey) VALUES ('ValUser',
'ValidationUser')`, idempotent (`NOT EXISTS` guard) — `ValidationUser` normalizes via
`_norm_field_token` to `validationuser`, the exact sensitive `FieldKey` seeded by migration
`0035`. Committed `1bd0135`, applied to INT cleanly (no schema drift — this is a data-only
insert into an existing table, same pattern as `0035`'s `Permission` row).

Restarted the dev server again (clears the 1-hour `index_field_mappings` SimpleCache and any
stale per-workitem `media_info_{wid}` cache entries so the new mapping takes effect
immediately). Recreated the throwaway `test.task8.noperm` user, then scanned **all 40**
`compass.01_Invoice_SAP` workitems on the first page via `/api/get_media_info/<wid>` as
`ben.streich` — zero errors (the mapping loads and is consumed correctly by every request),
but **none of the 40 currently have a live `ValUser` value from Octo**. Every one is at
`current_stage: "Validation"` — i.e. none has actually been validated yet, and "Validation
User" is almost certainly an audit field Octo only populates once a human completes that
step. This is not a gap in the mapping or the gating code: `strip_sensitive_from_detail`
was already unit-tested in Task 5 against a literal `"Validation User"`/`ValidationUser` key
and correctly strips it; the migration is now live and loads without error; there is simply
no real document yet whose Octo extraction has actually produced this field. Did **not**
fabricate fake Octo data to force an artificial end-to-end demo. Deleted the throwaway user
again afterward — confirmed 0 remaining rows.

**Net effect: both owner-only data actions (1 and 2) from the original plan are now done.**
The only genuinely-live end-to-end proof still pending is the panel/CSV surfaces
specifically, and that will happen automatically the first time a real
`compass.01_Invoice_SAP` document gets validated in Octo — no further action needed on the
code or config side.
