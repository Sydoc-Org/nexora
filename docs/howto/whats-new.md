# What's New page — curating release notes

The `/whats_new` page (profile dropdown → "What's New", or Ctrl+K) shows
**curated, user-facing** release notes — not the raw `CHANGELOG.md`, which
stays the dev-facing record. Users get a red badge dot (header avatar +
dropdown item) when a release newer than their seen-marker has entries their
permissions can see; opening the page clears it.

## The release routine step

When promoting `[Unreleased]` to a version in `CHANGELOG.md`, also:

1. Open `nx_lib/whats_new.py` and prepend a release dict to `RELEASES`
   (newest first): version string (must match `nx_lib/version.py`), ISO date,
   and a handful of entries.
2. Per entry: `title` + `body` (1–2 sentences, plain language, wrapped in
   `_( ... )` — the module aliases `lazy_gettext` as `_` so pybabel extracts
   and the session locale applies), optional `perm` (permission code — the
   entry is hidden from users without it; `None` = everyone), optional
   `endpoint` (`url_for` name for a "Try it" link) and `icon`
   (font-awesome name without the `fa-` prefix).
3. Run the translation cycle (`/nx-i18n` or `docs/howto/babel.md`) and fill
   the new de/fr/it msgstrs — the translation tests fail the push otherwise.

Curate ruthlessly: only what a user can see or do differently. Internal
refactors, dev tooling, and ops changes don't belong here.

## Mechanics

- Badge state: `dbo.Users.whats_new_seen_version` (migration `0061`,
  `NVARCHAR(32) NULL` — `NULL` means never opened). Opening `/whats_new`
  stamps the running `__version__`.
- The badge compares **curated releases** against the marker, so bumping the
  app version without curating entries lights nothing.
- Filtering is per-entry via `has_permission`; releases whose entries are all
  filtered away disappear entirely. Everything is computed fresh per request
  (same idiom as permissions/ui_prefs — no session cache to go stale).
