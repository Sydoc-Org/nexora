# Design — Git → Confluence docs sync (one-way mirror)

> **Status:** approved design, 2026-06-11
> **Owner:** benstreich
> **Decisions taken with owner:** publish `docs/howto/*` + `docs/design/*` + `README.md` + `CONTRIBUTING.md` + `CHANGELOG.md`; archive existing hand-written Confluence pages (no reverse import); full mirror of the `nexora` space with git as the single source of truth; sync runs on push to `main` with a docs path filter.

## 1. Goal & guiding principle

The Confluence space `nexora` (https://sydocteam.atlassian.net/wiki/spaces/nexora, homepage id `323944774`) currently holds hand-maintained product documentation that drifts from the repo. After this change, **git is the only place documentation is written**; Confluence becomes a generated, read-only render of the repo docs, refreshed automatically when docs land on `main`.

**Design principle: Confluence pages are disposable render artifacts.** Identity, history, and review all live in git. We deliberately do *not* preserve Confluence page history across file/heading renames — git history is the history. This collapses most docs-as-code sync complexity (committed page-ID maps, rename detection) into a much simpler model: publish by title, label what we own, archive what we no longer publish.

## 2. Scope

Published (11 files today, plus the new runbook this project adds):

| Source | Confluence location |
|---|---|
| `README.md` | Space homepage (id 323944774) body + generated child index |
| `CONTRIBUTING.md` | Child of homepage |
| `CHANGELOG.md` | Child of homepage |
| `docs/howto/*.md` (7) | Children of a generated "How-to guides" page |
| `docs/design/*.md` (1) | Children of a generated "Design docs" page |

Explicitly **not** published: `docs/superpowers/**` (internal AI-workflow artifacts), `docs/releases/**`, `CLAUDE.md`, `AGENTS.md`, anything else.

Out of scope for v1 (none of the 11 files need them today — verified by full-file scan): image/attachment upload, Mermaid/PlantUML rendering. The converter stack supports both if docs gain them later; revisit then.

## 3. Tooling decision

**Engine: `hunyadi/md2conf`** (PyPI package `markdown-to-confluence`, v0.6.1 of 2026-06-02, pure Python 3.10+, actively maintained). Chosen after researching the field (June 2026) and adversarially cross-checking; the verdict survived.

What md2conf gives us natively (verified by source inspection, not just README):

- Folder tree → Confluence page tree (`--keep-hierarchy`; `index.md`/`README.md` becomes the directory's parent page).
- Relative-link rewriting between published files via its build index; GitHub-style heading anchors (`--heading-anchors`).
- "Generated" banner on every page (`--generated-by`, templated) — our "do not edit" notice.
- Per-page idempotency: content digest stored as a Confluence content property; unchanged pages produce **zero** updates (no version spam, no watcher-notification storms).
- Code-fence → code-macro mapping with language validation/fallback (unknown languages degrade to plain blocks rather than broken macros).
- Headless auth via env vars (`CONFLUENCE_DOMAIN`, `CONFLUENCE_USER_NAME`, `CONFLUENCE_API_KEY`, `CONFLUENCE_SPACE_KEY`).

Rejected alternatives (headline reasons; full comparison in the research record):

- **kovetskiy/mark** — no Windows binaries (goreleaser windows target disabled since 2022), no mirror semantics, per-file metadata headers required.
- **All marketplace GitHub Actions** (Telefonica, cupcakearmy, TTENGS, markdown-confluence) — Docker container actions run only on Linux runners; ours is self-hosted Windows without Docker.
- **@telefonica/markdown-confluence-sync CLI** — needs Node ≥18 (not on the runner), no documented change detection, TypeScript stack a Python team shouldn't own.
- **sphinxcontrib-confluencebuilder** — only tool with native archive semantics, but forces Sphinx/MyST ceremony onto plain Markdown and has documented table-conversion gaps. Documented fallback if md2conf ever dies (single maintainer is its main risk).
- **Raw atlassian-python-api + hand-rolled converter** — re-implements four years of conversion edge cases to avoid ~100 lines of reconcile code.

**The one gap we build ourselves: the mirror/reconcile step.** md2conf only publishes; it never archives. The driver script (§4) implements: enumerate space pages → diff against the just-published set → bulk-archive orphans via the v1 archive endpoint. Important constraints from API research:

- Archive (not trash, not delete) is v1-only: `POST /wiki/rest/api/content/archive` with `{"pages":[{"id":...}]}` — async, returns 202 + a long-task id to poll (`GET /wiki/rest/api/longtask/{id}`). No Python library wraps it; one authenticated POST. Batch ≤100 ids per call.
- Archiving (not trashing) also sidesteps open md2conf bug #275 (crash on `trashed` page status).
- The endpoint archives exactly the listed ids — no descendants flag; the reconcile must enumerate children explicitly.
- v2 `GET /pages` returns current **and** archived by default — always filter `status=current` when reconciling.
- Never archive the homepage (id 323944774); exclude it unconditionally.

## 4. Components

### 4.1 `scripts/confluence-publish.py` — the driver

A stdlib-argparse CLI following the house `scripts/` conventions (`main() -> int`, `[publish]`-tagged output, two-space detail lines, meaningful exit codes 0/1/2, errors to stderr with copy-pasteable remediation, lazy imports of heavy deps). Uses md2conf as a **library** for conversion/publishing and `requests` (already a runtime dep) for the reconcile endpoints.

Pipeline, in strict phase order (crash-consistency by re-runnability, not transactions):

1. **Stage** — assemble `var/confluence-stage/` (gitignored, wiped each run):
   - `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` copied to stage root (original filenames, so README's existing relative link to `CONTRIBUTING.md` resolves without rewriting).
   - `docs/howto/*.md` → `stage/howto/` + a generated `stage/howto/index.md` ("How-to guides": one-line-per-doc link list).
   - `docs/design/*.md` → `stage/design/` + generated `stage/design/index.md` ("Design docs").
   - Files are copied byte-exact (binary copy, no transcoding) — CHANGELOG contains an *intentional* mojibake literal ("Generali â€\" PDQM Report", documenting the 0011 bug) that must survive.
2. **Validate & convert (local, before any API write)** — run md2conf conversion on the whole stage; any conversion error fails the run before Confluence is touched. Pre-flight title resolution: every intended title (from each file's H1) must be unique within the staged set.
3. **Publish** — md2conf publishes the stage tree rooted at the space homepage; directories become parent pages. Intended: `README.md` at stage root becomes the homepage body (md2conf treats a directory's `README.md`/`index.md` as that directory's parent page — whether it applies this to the *root* page id we pass must be verified during implementation; fallback is a direct v2 `PUT /pages/323944774` of the converted README from the driver). Stateless title-matched mode (no page-id write-back into sources — staging copies are discarded anyway). md2conf's digest property skips unchanged pages.
4. **Label** — ensure every published page carries the `git-managed` label (v1 `POST /content/{id}/label`; v2 has no label write as of June 2026). Idempotent: adding an existing label is a no-op.
5. **Reconcile** — list current pages in the space (v2, `status=current`); compute:
   - *Orphans* = pages labeled `git-managed` that were not published this run → bulk-archive (≤100/batch, poll long task).
   - *Strays* = unlabeled pages (excluding homepage) → **warn loudly, do not touch** in steady state (the read-only space makes these near-impossible; see §6). The one exception is bootstrap mode, below.

Flags (house style):

| Flag | Behavior |
|---|---|
| `--dry-run` | Full plan printed (creates / updates / skips / archives), zero API writes. Conversion still runs — this is the CI-reviewable preview. |
| `--bootstrap` | First-run mode: archive **all** existing non-homepage pages in the space (the old hand-written docs — per owner decision they are archived, recoverable via Confluence UI), then publish fresh. Prompts per the PROD-confirmation convention; `--yes` skips. |
| `--yes` / `-y` | Skip confirmations (CI). |
| `--env-file PATH` | Credentials file, default `env/CONFLUENCE.env`. |

Error handling: HTTP 429 → honor `Retry-After`, exponential backoff with jitter; transient 5xx → same retry; stale-version on page update (400 *or* 409 — spec and field reports disagree) → re-read version and retry once; **401/403 → distinct loud error naming token expiry/rotation** (all Atlassian API tokens created after 2024-12 expire ≤365 days — annual rotation is an ops fact, §8). Single-threaded, sequential — rate-limit-safe by construction. A failed run leaves the space partially updated; the recovery story is "run it again" (every step is idempotent).

### 4.2 Credentials — `env/CONFLUENCE.env`

New gitignored file (covered by existing `*.env` rule), sanitised template committed as `env/CONFLUENCE.env.example`:

```
CONFLUENCE_DOMAIN="sydocteam.atlassian.net"
CONFLUENCE_PATH="/wiki/"
CONFLUENCE_USER_NAME="<bot account email>"
CONFLUENCE_API_KEY="<api token>"
CONFLUENCE_SPACE_KEY="nexora"
```

Parsed by the driver with the same simple KEY=VALUE reader the config loader uses; values exported into `os.environ` for md2conf. Separate from `env/INT.env` because the credentials are environment-independent (one Cloud site) and the CI job shouldn't need the full app secret set.

Auth decision: **dedicated bot user + unscoped API token via basic auth at the site URL.** Scoped tokens must call `api.atlassian.com/ex/confluence/{cloudId}/...` and their coverage of the four v1-only endpoints we need (archive, label add, space permissions) is unverified — unscoped at the site URL is the verified-safe choice. The sync needs `Archive` space permission plus standard add/edit.

### 4.3 `.github/workflows/confluence-docs.yml` — the trigger

Separate workflow (not a deploy.yml job — docs publishing must not couple to app deploys):

- `on: push: branches: [main]` with `paths: [docs/howto/**, docs/design/**, README.md, CONTRIBUTING.md, CHANGELOG.md, scripts/confluence-publish.py, .github/workflows/confluence-docs.yml]` + `workflow_dispatch`.
- `concurrency: group: confluence-sync` (queued run waits; no cancel of an active sync) — two syncs must never interleave (version races).
- `runs-on: self-hosted` (SYAPP01 runner). Steps: checkout → `pip install -r requirements-dev.txt` (brings md2conf) → copy `C:\sydoc\runner-secrets\CONFLUENCE.env` into workspace `env/` (same pattern as TEST.env; throw with a "provision once on the runner" message if missing) → `python scripts/confluence-publish.py --yes` → remove the copied env file in a `finally`-equivalent step.

Secrets stay runner-side files — this repo deliberately uses zero GitHub Actions secrets today; we keep that convention.

### 4.4 Dependency wiring

`markdown-to-confluence` added to the `[dev]` extra in `pyproject.toml` → `uv lock` → re-export **both** `requirements-dev.txt` and check `requirements.txt` unchanged (a stale export broke CI before). It must NOT go into runtime requirements: the Flask app never publishes docs. Prod is protected twice already (app installs only `requirements.txt`; robocopy excludes the rest); no `deploy.yml` exclude changes needed — `scripts/`, `.github/`, `docs/`, `var/` are all already excluded.

### 4.5 Tests — `tests/test_confluence_publish.py`

No-network unit tests:

- **Conversion smoke over the real corpus:** stage + convert all 11 real files; assert zero conversion errors. This is the regression net for md2conf upgrades.
- **Golden invariants** on generated storage XML (the repo-scan identified the traps): angle-bracket code spans (`<id>`, `<thead>`, `<script>`) XML-escaped; escaped pipes in `nx.md` tables survive as cell content; code fences inside ordered-list items don't break numbering (iis.md step 3, reporting.md steps 1–6); CHANGELOG's `## [Unreleased]` bracket headings render literally; the mojibake literal survives byte-exact; hard-wrapped paragraphs don't become `<br/>`; unicode (→ ∈ ≤ ✅ em-dashes) intact.
- **Driver logic:** staging assembly (file set, generated indexes), title-uniqueness pre-flight, reconcile set arithmetic (orphans/strays/homepage-exclusion), archive batching, 429/version-conflict retry paths (mocked transport).

### 4.6 Runbook — `docs/howto/confluence-sync.md`

New doc (which itself gets published — good first dogfood): how the pipeline works, bootstrap procedure, **token rotation runbook** (where the token lives on the runner, how to mint a new one, the ≤365-day expiry, what the 401 failure looks like), title-held-hostage-by-trash remediation, how to restore an archived page (UI-only — no REST unarchive exists), and "how do I edit the docs" guidance for Confluence-first readers (edit in git, here's the repo link).

## 5. Confluence tree after sync

```
nexora space
└── Homepage 323944774  <- README.md body + child index ("do not edit" banner)
    ├── Contributing to nexora        <- CONTRIBUTING.md
    ├── Changelog                     <- CHANGELOG.md
    ├── How-to guides                 <- generated index
    │   ├── Babel translation workflow
    │   ├── Confluence docs sync      <- the new runbook
    │   ├── Database migrations
    │   ├── IIS deployment setup
    │   ├── ngrok setup (SYAPP01)
    │   ├── nx — the nexora dev CLI
    │   ├── Reporting
    │   └── Working with Claude Code on nexora
    └── Design docs                   <- generated index
        └── Design — AI assistant in the Reporting page
```

Titles come from each file's H1 (house style: exactly one `# Title` on line 1 — verified across all 11). The admin-page link to the Confluence overview (`templates/admin/admin_overview.html`) keeps working — the homepage id never changes.

Every page opens with an info-panel banner: *"This page is generated from the nexora git repo (`<path>` @ https://github.com/Sydoc-Code/nexora). Do not edit here — changes will be overwritten by the next sync. To change it, edit the file in git."*

## 6. Making "read-only for humans" real

Banner alone doesn't stop good-faith edits (the most-reported social failure of these pipelines — silent loss of a PM's typo fix). Enforcement: **one-time manual change in Space Settings → Permissions**: humans keep read, lose page add/edit/archive; the bot account keeps full write. Manual because it's a single irreversible-ish admin action better done consciously than scripted (the v1 permission-mutation API exists if we later automate). The runbook documents the exact clicks. If the tenant has been migrated to Atlassian's new RBAC space roles (check `GET /wiki/api/v2/space-role-mode`), the equivalent is Viewer for everyone + bot as Manager.

Manual-edit drift before the flip (or by a space admin): not detected in v1 — the next content change in git overwrites it silently. Accepted: the read-only flip happens at go-live, the window is hours, and the banner warns. (md2conf's digest-skip means an *unchanged* git file never overwrites a manually-edited page — drift on a never-again-touched page would persist; another reason the permission flip is required, not optional.)

## 7. What we deliberately do NOT do (YAGNI)

- No committed page-ID mapping, no rename detection: a renamed file or changed H1 = new page + old page archived. Git is the history; Confluence page history/comments are expendable (space is read-only — comments shouldn't accumulate there anyway).
- No two-way sync, no drift detection diffs, no PR-preview publishing.
- No image/attachment pipeline (nothing to attach today — §2).
- No notification suppression beyond idempotency (Cloud has no working API flag anyway).
- No automated space-permission management.
- No PROD/INT split — there is exactly one Confluence site; the sync runs from `main` only.

## 8. Operational risks & mitigations

| Risk | Mitigation |
|---|---|
| API token expires (hard ≤365d since 2026) | Runbook + distinct 401 error message; calendar reminder at token creation; failure mode is a red workflow run, not silent rot |
| md2conf single-maintainer risk | Pinned version; conversion smoke test over the real corpus gates upgrades; sphinxcontrib-confluencebuilder documented as fallback engine |
| Conversion edge case slips through | Golden-invariant tests built from the actual repo-scan findings (§4.5); `--dry-run` preview |
| Half-updated space after mid-run failure | Strict phase ordering + idempotent re-run as recovery; concurrency group prevents interleaving |
| Title collision with a trashed page | Pre-flight title check; runbook documents purge-from-trash remediation |
| Old archived pages polluting search | Archive (excluded from quick search) + `git-managed` labels make the live population auditable via CQL |
| Bootstrap archives something valuable | Archiving is recoverable (Confluence UI restore); bootstrap prints the full page list and prompts before acting |

## 9. Rollout

1. **Owner (manual, prerequisites):** create bot account + API token; verify plan tier supports archiving (Standard+); provision `C:\sydoc\runner-secrets\CONFLUENCE.env`; local `env/CONFLUENCE.env` for dev-box runs.
2. **Build** driver + tests + workflow + runbook (CI workflow lands disabled-by-absence — it only fires on push to `main`, so merging the feature branch *is* the enablement).
3. **Bootstrap from dev box:** `--dry-run` review → `--bootstrap` run → eyeball the space (especially reporting.md, the largest/most complex page, and nx.md's escaped-pipe tables).
4. **Flip space permissions** to read-only for humans.
5. **Steady state:** push to `main` touching a published path → workflow syncs.

## 10. Success criteria

- Editing `docs/howto/nx.md` on `main` updates the "nx — the nexora dev CLI" page within minutes, and **only** that page (idempotency: all other pages report "up-to-date", zero version bumps).
- Deleting a published file archives its page on the next sync.
- Second consecutive run with no git changes performs zero page writes.
- All 11 current files render in Confluence without macro errors, broken tables, or mangled code blocks.
- A human attempting to edit any synced page is blocked by space permissions and sees the banner pointing at git.
