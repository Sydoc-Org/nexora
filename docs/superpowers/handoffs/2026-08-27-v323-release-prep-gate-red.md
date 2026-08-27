# Handoff — v3.2.3 release prep done, deploy blocked on 6 red dashboard tests

**Date:** 2026-08-27 · **Branch:** `v3.2.3.1` (main checkout, no worktree) · **32 commits ahead of
`origin/v3.2.3.1`, unpushed** · owner pushes · **deploy authorized by the owner but NOT started —
the gate is red.**

**Prior handoff:**
[`2026-08-27-white-label-executed-merged.md`](2026-08-27-white-label-executed-merged.md) — peer
session `hermes` executed white-label phase 4 and merged `feat/white-label` into `v3.2.3.1`
(`057a2ebd`). That merge landed **after** this session's release commit, which is how the two
gaps below opened.

## TL;DR — what the next session must do

1. **Diagnose the 6 failing tests below.** They pass in isolation, fail in the full gate, and the
   failing set moved 8 → 6 between two identical runs.
2. Then, and only then, deploy: consolidate `v3.2.3.1` → `v3.2.3`, push, PR to `main`, babysit CI
   through the PROD deploy (`/deploy` skill). The owner already said go.

---

## THE RED TESTS (what was asked to be written down)

Gate command — run it **exactly**, no extra flags (ad-hoc flags manufacture phantom failures):

```
python scripts/test_db_reset.py
python -m pytest tests --ignore=tests/e2e
```

Last full run: **6 failed, 2106 passed, 22 skipped** (492 s). All six are in
`tests/integration/test_dashboard_routes.py`:

| Test | Assertion that fires |
|---|---|
| `test_recent_activity_forwards_row_client_as_hint` | `assert [] == [(1216, 'ms02')]` |
| `test_recent_activity_skips_row_when_workitemdata_lookup_fails` | `assert [] == [111]` |
| `test_recent_activity_strips_sensitive_fields_without_perm` | `IndexError: list index out of range` |
| `test_recent_activity_rows_include_client_key` | `IndexError: list index out of range` |
| `test_recent_activity_route_derives_granted_pairs_not_cross_product` | `assert 0 == 1` |
| `test_processed_over_time_error_response_is_not_cached` | `assert 200 == 500` |

Exact list re-extractable any time from the last run's report:

```
python -c "import xml.etree.ElementTree as ET; t=ET.parse('var/test-results/junit.xml'); print('\n'.join(f\"{tc.get('classname')}::{tc.get('name')}\" for tc in t.iter('testcase') if tc.find('failure') is not None or tc.find('error') is not None))"
```

### What is known

- **They pass in isolation:** `python -m pytest tests/integration/test_dashboard_routes.py` → 22
  passed. Only the full suite reddens them.
- **The set is not stable:** the first full run after hermes's merge failed 8, the next 6 (the two
  that stopped failing were `test_whats_new_routes.py::test_admin_sees_every_entry`, fixed here,
  plus one more that did not recur). Order/state dependence, not a deterministic break.
- **Every symptom is "the client registry is empty":** every failure is *no rows where `ms02` rows
  were expected*, and the 200-instead-of-500 is the same thing (no client ⇒ no query ⇒ no error
  path). `1216` is the id that collides between the Octo and MS02 runtimes, so these tests are
  specifically exercising MS02 routing.
- **The likely cause is a TEST-schema gap, not the app.** hermes's `0079_clients_registry.sql`
  moved the client registry out of the hardcoded `nx_lib/clients.py::CLIENTS` dict and into
  `dbo.Clients`. **`dbo.Clients` does not exist in `sql/test/schema.sql` at all** (verified:
  `grep -c "dbo.Clients" sql/test/schema.sql` → 0), and no dashboard test stubs the registry.
  `nx_lib/clients.py` builds `CLIENTS` **at import time, once per process**, and its own comment
  says the registry "silently collapses to 'default' only" when `dbo.Clients` cannot be read —
  which is exactly `ms02` disappearing.
- **Unverified:** why isolation passes. Import-time build means the read fails the same way in
  both cases, so something in the full run must rebuild or replace the registry (a peer test that
  mocks `engine_nexora_db.raw_connection` and re-imports, most likely one of hermes's new
  `/admin/clients` tests). **Confirm this before fixing** — the fix differs:
  - *If it is the schema gap:* mirror `dbo.Clients` into `sql/test/schema.sql` and seed the
    `default` + `ms02` rows in `sql/test/seed.sql`, mirroring `0079_clients_registry.sql`. This is
    the same class of gap as the two already fixed this session.
  - *If it is cross-test contamination:* the dashboard tests should pin the registry explicitly
    (monkeypatch `nx_lib.clients.CLIENTS`) instead of inheriting process state.

**Do not dismiss these as flake without doing that.** They are red on a build that is about to go
to production, and the affected route is the dashboard's recent-activity feed for MS02.

---

## What this session finished (committed)

| Commit | What |
|---|---|
| `dc343bcf` | Reporting **source visualizer** — click a Sources rail card for the tables + ER diagram behind it (`GET /api/reporting/sources/<id>/schema`, `nx_lib/reporting/db_schema.py`, new `reporting.sources.schema` permission, migration `0079_add_reporting_source_schema_permission.sql`) |
| `3c9b84e6` | Visualizer narrowed to **only the tables a source reads** (registry seed → view deps → one FK hop, else non-empty tables); view→table edges drawn dashed |
| `7f67c58c`, `29886a26` | Generali DB restructure plan + link to issue **#220** (owner parked it — not a priority) |
| `d8190055` | **`scripts/test_db_reset.py` wipes NEXORA_TEST first** — the hand-maintained FK-safe DROP order in `sql/test/schema.sql` could not know about tables another branch had applied, so every reset died on `dbo.Organizations`. Third time that list broke; it no longer needs maintaining. |
| `188bbd66` | Merge of `origin/v3.2.3.1` (the `ActivityInstancesToIgnore` fix) |
| `e72baff0` | **Release promotion:** version `3.2.3` in `version.py` + `pyproject.toml` + `uv.lock`; CHANGELOG `[Unreleased]` → `[3.2.3] - 2026-08-27` (duplicate `### Added`/`### Changed`/`### Fixed` headings folded, 54 entries, none lost); 8 curated What's New entries with de/fr/it; three pre-existing docs defects that would have failed the Confluence publish |

**Uncommitted at handoff time** (all release-completeness work for hermes's merge — commit it):

- `nx_lib/whats_new.py` — 2 more entries for hermes's work (per-organization branding; the
  Clients/Processes onboarding pages). `whats_new.py` had **nothing** for white-label, and the
  badge only lights on curated entries, so without these the feature ships silently.
- `translations/{de,fr,it}` + `messages.pot` — those 2 entries translated and compiled.
- `sql/test/seed.sql` — **5 of the 6 permission codes from `0080_white_label_admin_permissions.sql`**
  (`admin.view.clients`, `admin.edit.clients`, `admin.view.processes`, `admin.edit.processes`,
  `admin.edit.organization.branding`). `admin.view.organizations` was already seeded — adding it
  again violates the unique key and kills the whole seed, so do not "complete" the list.

## Deploy state — read before pushing

- **Precondition met.** hermes merged into `v3.2.3.1` locally (`057a2ebd`), *not* into
  `origin/v3.2.3` — a monitor watching that ref never fired and is now pointless. `origin/v3.2.3`
  is still `e007ff25`; `origin/main` is still the v3.2.2 merge `78592ce8`.
- **PROD is 12 migrations behind** (`0071`–`0081`). `deploy.yml` applies them automatically
  *before* stopping the app pool. Two are destructive drops running unattended against production
  (`0072_drop_decapitated_tables.sql`, `0075_decapitate_legacy_mapping_tables.sql`) — **take a PROD
  backup first.**
- **Duplicate migration number `0079`** — this session's `0079_add_reporting_source_schema_permission.sql`
  and hermes's `0079_clients_registry.sql` (the parallel-session race). Both are applied on INT and
  both are listed as pending for PROD. `db-migrate.py` applies in `sorted()` filename order, so it
  is deterministic, and the two are independent (a permission INSERT vs a new table). **Leave them
  alone** — renumbering an applied migration re-applies it and churns checksums. Cosmetic only.
- **11 env keys are declared in `PROD.env.example` but missing from the server file** — paste into
  `\\syapp01\d$\sydoc\nexora\env\PROD.env` by hand (`python scripts/env-sync.py` prints them). They
  are also unset locally, so the committed defaults were never exercised anywhere — sanity-check
  `AI_MODEL=claude-sonnet-4-6` against what PROD should run before pasting. None are from this
  session; they have accumulated across cycles.

## Gotchas this session paid for

1. **Never write a Windows path into a shell heredoc.** `docs/howto/iis.md` had
   `D:\sydoc\nexora\var\` stored as `D:\sydoc` + newline + `exora` + **U+000B** + `ar` — someone
   wrote it through a tool that interpreted the escapes. U+000B is not a legal XML character, so
   the Confluence publish could not convert the page. I reproduced the same corruption while
   writing the fix. Build backslashes with `chr(92)` in a file written by the Write tool, never a
   `<<'EOF'` heredoc.
2. **Bare `<tag>`-looking text in published docs breaks the Confluence publish**, not just lints:
   `<dimension>` in `reporting.md` and `"<name> (copy)"` in the changelog both parsed as unclosed
   HTML. Backtick them. `tests/test_confluence_publish.py` is the golden test that catches it.
3. **A relative link out of the staged doc tree kills the whole file** —
   `architecture-conventions.md` linked `../../CLAUDE.md`, which is not in the published set.
4. `git status` showing ` M` on `sql/NexoraDB/Tables/*.sql` with an **empty `git diff`** is the
   stale-dump/CRLF situation, not real drift. Commit with `SQL_SYNC_SKIP=1` and a pathspec; do not
   try to "fix" the files.
5. Two untracked dumps (`dbo.KundenmagazinIssues.sql`,
   `dbo.KundenmagazinIssueOrganizations.sql`) belong to a third party's INT work with no migration
   on this branch. Leave them.
