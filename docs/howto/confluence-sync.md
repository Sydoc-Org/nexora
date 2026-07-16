# Confluence docs sync

The Confluence space [nexora](https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774)
is a **generated, read-only mirror** of the docs in this repo. Git is the only
place documentation is written; a sync publishes it to Confluence.

## What gets published

| Source in git | Confluence |
|---|---|
| `README.md` | Space homepage |
| `CONTRIBUTING.md`, `CHANGELOG.md` | Children of the homepage |
| `docs/howto/*.md` | Under "How-to guides" |
| `docs/design/*.md` | Under "Design docs" |

Everything else (`docs/superpowers/`, `docs/releases/`, `CLAUDE.md`, ...) stays
git-only. To change a published page, edit the Markdown file and merge to
`main` — the workflow `.github/workflows/confluence-docs.yml` republishes
automatically (path-filtered; also runnable via *Run workflow* in Actions).

## How it works

`scripts/confluence-publish.py` stages the publish set into
`var/confluence-stage/`, converts and publishes with
[md2conf](https://github.com/hunyadi/md2conf) (folder tree → page tree,
relative links rewritten, content-hash skip for unchanged pages, "do not edit"
banner on every page), then reconciles: every published page carries the
`git-managed` label; labeled pages that are no longer in git get **archived**
(never deleted). Renaming a file or its H1 creates a fresh page and archives
the old one — page history lives in git, not Confluence.

Local commands (credentials in `env/CONFLUENCE.env`, template in
`env/CONFLUENCE.env.example`):

```powershell
python scripts/confluence-publish.py --dry-run    # full plan, zero writes
python scripts/confluence-publish.py --yes        # what CI runs
python scripts/confluence-publish.py --bootstrap  # FIRST RUN ONLY, see below
```

## Credential account

The sync currently runs as **benjamin.streich@sydoc.ch** (personal account).
This is fine to start, but should be migrated to a dedicated service account
(e.g. `noreply.sy@sydoc.ch`) once that account has a Confluence product seat
in the Atlassian org admin. Migration = create token on the service account,
update both credential files, revoke the old token.

The runner reads its copy from `C:\sydoc\runner-secrets\CONFLUENCE.env` on
SYAPP01 (provisioned 2026-07-16, CI verified end-to-end). When rotating the
token, update **both** that file and your local `env/CONFLUENCE.env`.

## Token rotation (yearly!)

Atlassian API tokens expire after at most 365 days. When the sync fails with
the 401 token message:

1. Log in as the sync account → <https://id.atlassian.com/manage-profile/security/api-tokens>
   → create a new **unscoped** token ("Create API token", *not* "with scopes").
   Unscoped tokens start with `ATATT`; scoped ones start with `ATCTT` and
   silently fail (see Troubleshooting).
2. Update `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01 (and your local
   `env/CONFLUENCE.env` if you run the script locally).
3. Re-run the workflow (*Actions → Confluence docs sync → Run workflow*).
4. Set a reminder for next year; revoke the old token.

## Bootstrap (done 2026-06-11 — for reference / disaster recovery)

`--bootstrap` archives **all** existing non-homepage pages in the space (the
pre-sync hand-written docs were archived this way; recover any of them via
Confluence → Space settings → Archived pages), then publishes fresh from git.

**Pending (owner):** after runner secrets are provisioned and CI is verified,
make the space read-only for humans: Space settings → Permissions → remove page
add/edit/archive from user groups, keep full write for the sync account only.

## Troubleshooting

- **403 "caller cannot access Confluence" / 404 on the spaces endpoint** —
  the token is being ignored and the request runs as *anonymous*. Almost
  always a **scoped** API token (`ATCTT...` prefix): scoped tokens don't work
  with Basic auth against the site domain. Mint an unscoped token (`ATATT...`)
  and update both credential files. (Diagnostic: the API responds identically
  with and without the `Authorization` header.) This is not a seat/permission
  problem — don't chase product access in org admin (been there, 2026-07-16).
- **"duplicate page title"** — two source files share an H1. Titles must be
  unique per space; change one heading.
- **"A page with this title already exists" from the API** — a *trashed* page
  holds the title hostage. Space settings → Trash → purge or rename it.
- **Archived page needs to come back** — restore is UI-only (no REST
  endpoint): Space settings → Archived pages → restore. If git still publishes
  a page with that title, restore will collide — rename one.
- **Page looks stale** — check the Actions run; the sync only touches pages
  whose content hash changed. `--dry-run` locally shows what it would do.
- **Conversion failure on a new doc** — `pytest tests/test_confluence_publish.py`
  runs the same conversion locally; the golden-invariant tests pin the
  Markdown features the corpus relies on.

## See also

- `docs/superpowers/specs/2026-06-11-confluence-docs-sync-design.md` — design and decisions
- `scripts/confluence-publish.py` — the driver
- `.github/workflows/confluence-docs.yml` — the trigger
