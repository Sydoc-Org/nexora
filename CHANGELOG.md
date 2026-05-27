# Changelog

All notable changes to nexora are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `LICENSE` (proprietary Sydoc notice)
- `CHANGELOG.md`
- `CONTRIBUTING.md` with naming, branch, and commit conventions
- `.editorconfig` for cross-editor consistency
- `.python-version` pinning Python 3.13.9

### Removed
- Empty placeholder folders: `cleanup/`, `export-help/`, `generali-import/`, `news/`
- Deprecated `environment_transfer_queries.tmp.sql` (superseded by `sql/_migrations/`)

### Changed
- Expanded `README.md` with onboarding overview and quick links
- Dependency management migrated to uv with committed `uv.lock`. `requirements.txt` and `requirements-dev.txt` are now generated artifacts (kept for the IIS/wfastcgi deploy path).
- Git hooks now managed via the pre-commit framework (`.pre-commit-config.yaml`). Custom hook scripts under `scripts/git-hooks/` are wrapped as `repo: local` entries to preserve behaviour. `install-git-hooks.ps1` becomes a deprecation shim that calls `pre-commit install` for you.
- Conventional Commits enforced via gitlint commit-msg hook (`.gitlint`).

## [2.5.60] - 2026-05-XX
- Repository restructure (PRs #84, #85): `ops/` (prod-scheduled) vs `scripts/` (dev/manual), SQL migrations workflow, branch-name guard.
