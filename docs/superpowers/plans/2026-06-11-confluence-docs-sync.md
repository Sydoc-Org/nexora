# Git → Confluence Docs Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-way mirror that publishes `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` to the `nexora` Confluence space on every push to `main`, archiving pages that no longer exist in git.

**Architecture:** A staging step assembles the publish set into `var/confluence-stage/`; `md2conf` (PyPI `markdown-to-confluence`) converts and publishes the tree under the space homepage with content-hash idempotency and a "do not edit" banner; a custom reconcile step labels published pages `git-managed` and bulk-archives orphans via the v1 archive endpoint. Driven by `scripts/confluence-publish.py` (house `scripts/` conventions), triggered by `.github/workflows/confluence-docs.yml` on the self-hosted Windows runner.

**Tech Stack:** Python 3.13, `markdown-to-confluence==0.6.1` (dev extra), `requests` (already runtime dep), GitHub Actions self-hosted runner, Confluence Cloud REST v1+v2.

**Spec:** `docs/superpowers/specs/2026-06-11-confluence-docs-sync-design.md` — read it first.

**Branch:** `feat/confluence-docs-sync` (worktree `.claude/worktrees/confluence-docs-sync`).

**Commit note:** the `sql-migrate-int` pre-commit hook fails on this Windows clone due to known INT checksum CRLF drift. Commit with `SQL_SYNC_SKIP=1 git commit ...` (the documented escape hatch; nothing in this plan touches SQL).

---

## File map

| File | Role |
|---|---|
| `scripts/confluence-publish.py` | Create — driver CLI: stage → convert → publish → label → reconcile |
| `tests/test_confluence_publish.py` | Create — no-network unit tests + conversion smoke over the real corpus |
| `.github/workflows/confluence-docs.yml` | Create — push-to-main trigger, path-filtered |
| `env/CONFLUENCE.env.example` | Create — sanitised credential template |
| `docs/howto/confluence-sync.md` | Create — runbook (token rotation, bootstrap, troubleshooting) |
| `pyproject.toml` | Modify — add `markdown-to-confluence==0.6.1` to `[project.optional-dependencies] dev` |
| `requirements-dev.txt` | Regenerate via `uv export` |
| `CHANGELOG.md` | Modify — fix duplicate `### Fixed` under `[Unreleased]`; add feature entry |
| `CLAUDE.md` | Modify — line 5 wording + "Keeping docs in sync" section |
| `docs/howto/claude-workflow.md` | Modify — Confluence section wording |

---

### Task 1: Dependency + md2conf CLI spike

md2conf's CLI flag names and local-conversion mode are research-sourced; this task pins them against the installed reality. **Record the actual flag names — later tasks use `--root-page`, `--keep-hierarchy`, `--heading-anchors`, `--generated-by`, `--local`; adjust those constants everywhere if `--help` disagrees.**

**Files:**
- Modify: `pyproject.toml:37-50` (dev extra)
- Regenerate: `requirements-dev.txt`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, append to the `dev` list (after `"gitlint-core==0.19.1",`):

```toml
    "markdown-to-confluence==0.6.1",
```

- [ ] **Step 2: Lock and export**

```powershell
uv lock
uv sync --extra dev
uv export --format requirements-txt --no-hashes --extra dev --output-file requirements-dev.txt
```

Expected: `uv.lock` and `requirements-dev.txt` change; `git diff requirements.txt` is **empty** (runtime untouched — verify this explicitly).

- [ ] **Step 3: Spike — record the CLI surface**

```powershell
.\venv\Scripts\python.exe -m md2conf --help
```

Expected: usage text. Confirm (and write down in the task notes) the real names for: root page id flag, hierarchy flag, heading-anchor flag, generated-by/banner flag, local-conversion flag, and whether env vars `CONFLUENCE_DOMAIN` / `CONFLUENCE_PATH` / `CONFLUENCE_USER_NAME` / `CONFLUENCE_API_KEY` / `CONFLUENCE_SPACE_KEY` are documented. If any later-task constant mismatches, fix it when you get there.

- [ ] **Step 4: Spike — local conversion of the simplest doc**

```powershell
mkdir var\md2conf-spike; copy docs\howto\ngrok.md var\md2conf-spike\
.\venv\Scripts\python.exe -m md2conf var\md2conf-spike --local
Get-ChildItem var\md2conf-spike
```

Expected: exit 0 and a generated Confluence Storage Format file (`.csf`/`.xml`) next to the source. Open it; confirm the PowerShell fence became a `<ac:structured-macro ac:name="code">` block. Delete `var\md2conf-spike` afterwards.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock requirements-dev.txt
SQL_SYNC_SKIP=1 git commit -m "build(deps): add markdown-to-confluence to dev extra for Confluence docs sync"
```

---

### Task 2: Fix the pre-existing CHANGELOG duplicate heading

`## [Unreleased]` contains `### Fixed` twice (lines 318 and 438) — a Keep-a-Changelog violation that would also produce a duplicate heading anchor in Confluence. Found during the docs scan; fix it before the corpus becomes test fixtures.

**Files:**
- Modify: `CHANGELOG.md:318-538`

- [ ] **Step 1: Merge the two Fixed sections**

Cut the entire bullet block under the **second** `### Fixed` (line 438, bullets run until the `### Removed` heading at line 539) and append those bullets to the end of the **first** `### Fixed` section (immediately before the `### Changed` heading at line 324). Delete the now-empty second `### Fixed` heading line. Line numbers shift after editing — locate by heading text, not absolute number.

- [ ] **Step 2: Verify**

```powershell
(Select-String -Path CHANGELOG.md -Pattern '^### Fixed').Count
```

Expected: one occurrence **within the `[Unreleased]` block** (total count across the file may be higher — released sections legitimately have their own). Quick check: `git diff CHANGELOG.md` shows only moved lines, no content edits.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
SQL_SYNC_SKIP=1 git commit -m "docs(changelog): merge duplicate Fixed sections under Unreleased"
```

---

### Task 3: Driver skeleton — staging, titles, index generation (TDD)

**Files:**
- Create: `scripts/confluence-publish.py`
- Create: `tests/test_confluence_publish.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_confluence_publish.py`:

```python
"""Unit tests for scripts/confluence-publish.py (no network access)."""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "confluence_publish", REPO_ROOT / "scripts" / "confluence-publish.py"
)
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


class TestExtractTitle:
    def test_h1_on_first_line(self):
        assert cp.extract_title("# Reporting\n\nBody.") == "Reporting"

    def test_h1_with_inline_code_and_dash(self):
        assert cp.extract_title("# nx — the nexora dev CLI\n") == "nx — the nexora dev CLI"

    def test_missing_h1_raises(self):
        with pytest.raises(ValueError, match="no H1"):
            cp.extract_title("body without heading\n")


class TestStaging:
    def test_stage_docs_layout(self, tmp_path):
        staged = cp.stage_docs(REPO_ROOT, tmp_path)
        rel = sorted(str(s.staged.relative_to(tmp_path)).replace("\\", "/") for s in staged)
        # root files keep their names; dirs map to howto/ + design/; indexes generated
        assert "README.md" in rel
        assert "CONTRIBUTING.md" in rel
        assert "CHANGELOG.md" in rel
        assert "howto/index.md" in rel
        assert "design/index.md" in rel
        assert "howto/ngrok.md" in rel
        assert "design/reporting-ai-assistant.md" in rel
        # nothing outside the publish set leaks in
        assert not any(r.startswith("superpowers") for r in rel)

    def test_staged_copies_are_byte_exact(self, tmp_path):
        cp.stage_docs(REPO_ROOT, tmp_path)
        src = (REPO_ROOT / "CHANGELOG.md").read_bytes()
        assert (tmp_path / "CHANGELOG.md").read_bytes() == src

    def test_stage_wipes_previous_content(self, tmp_path):
        leftover = tmp_path / "howto" / "deleted-doc.md"
        leftover.parent.mkdir(parents=True)
        leftover.write_text("# Old\n")
        cp.stage_docs(REPO_ROOT, tmp_path)
        assert not leftover.exists()


class TestIndexGeneration:
    def test_index_lists_titles_sorted_with_links(self):
        entries = [("Zeta guide", "zeta.md"), ("Alpha guide", "alpha.md")]
        text = cp.generate_index("How-to guides", entries)
        assert text.startswith("# How-to guides\n")
        alpha = text.index("[Alpha guide](alpha.md)")
        zeta = text.index("[Zeta guide](zeta.md)")
        assert alpha < zeta


class TestPreflight:
    def test_duplicate_titles_rejected(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("# Same Title\n")
        b.write_text("# Same Title\n")
        staged = [
            cp.StagedFile(source=a, staged=a, title="Same Title"),
            cp.StagedFile(source=b, staged=b, title="Same Title"),
        ]
        with pytest.raises(SystemExit):
            cp.preflight_titles(staged)

    def test_real_corpus_titles_unique(self, tmp_path):
        staged = cp.stage_docs(REPO_ROOT, tmp_path)
        cp.preflight_titles(staged)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: FAIL — `FileNotFoundError` / `AttributeError` (module doesn't exist yet).

- [ ] **Step 3: Write the driver skeleton**

`scripts/confluence-publish.py`:

```python
"""Publish git-tracked docs to the nexora Confluence space (one-way mirror).

Usage:
  python scripts/confluence-publish.py --dry-run
  python scripts/confluence-publish.py --yes
  python scripts/confluence-publish.py --bootstrap          # first run: archive ALL old pages
  python scripts/confluence-publish.py --env-file env/CONFLUENCE.env

Design doc: docs/superpowers/specs/2026-06-11-confluence-docs-sync-design.md
Runbook:    docs/howto/confluence-sync.md

Exit codes: 0 ok, 1 publish/reconcile failure, 2 config/usage error.
"""

import argparse
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_DIR = REPO_ROOT / "var" / "confluence-stage"
DEFAULT_ENV_FILE = REPO_ROOT / "env" / "CONFLUENCE.env"

SPACE_KEY = "nexora"
OWNED_LABEL = "git-managed"
ARCHIVE_BATCH = 100

ROOT_FILES = ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")
DIR_MAP = {"docs/howto": "howto", "docs/design": "design"}
INDEX_TITLES = {"howto": "How-to guides", "design": "Design docs"}

GENERATED_BY = (
    "This page is generated from the nexora git repo "
    "(https://github.com/Sydoc-Code/nexora) - do not edit here; "
    "changes will be overwritten by the next sync. To change it, edit the "
    "corresponding Markdown file in git."
)

REQUIRED_ENV_KEYS = (
    "CONFLUENCE_DOMAIN",
    "CONFLUENCE_USER_NAME",
    "CONFLUENCE_API_KEY",
    "CONFLUENCE_SPACE_KEY",
)


@dataclass
class StagedFile:
    source: Path  # absolute path of the original in the repo
    staged: Path  # absolute path of the staged copy
    title: str  # H1 text == Confluence page title


def extract_title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip():
            break
    raise ValueError("no H1 on first non-empty line")


def generate_index(title: str, entries: list[tuple[str, str]]) -> str:
    lines = [f"# {title}", ""]
    for page_title, filename in sorted(entries, key=lambda e: e[0].lower()):
        lines.append(f"- [{page_title}]({filename})")
    return "\n".join(lines) + "\n"


def stage_docs(repo_root: Path, stage_dir: Path) -> list[StagedFile]:
    """Assemble the publish set into stage_dir (wiped first). Byte-exact copies."""
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    staged: list[StagedFile] = []

    def copy_one(src: Path, dst: Path) -> StagedFile:
        data = src.read_bytes()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        title = extract_title(data.decode("utf-8"))
        return StagedFile(source=src, staged=dst, title=title)

    for name in ROOT_FILES:
        staged.append(copy_one(repo_root / name, stage_dir / name))

    for src_dir, dst_name in DIR_MAP.items():
        entries: list[tuple[str, str]] = []
        for md in sorted((repo_root / src_dir).glob("*.md")):
            sf = copy_one(md, stage_dir / dst_name / md.name)
            staged.append(sf)
            entries.append((sf.title, md.name))
        index_path = stage_dir / dst_name / "index.md"
        index_text = generate_index(INDEX_TITLES[dst_name], entries)
        index_path.write_text(index_text, encoding="utf-8", newline="\n")
        staged.append(
            StagedFile(source=index_path, staged=index_path, title=INDEX_TITLES[dst_name])
        )

    return staged


def preflight_titles(staged: list[StagedFile]) -> None:
    seen: dict[str, Path] = {}
    for sf in staged:
        if sf.title in seen:
            print(
                f"[publish] ERROR: duplicate page title '{sf.title}' from "
                f"{seen[sf.title]} and {sf.source}. Confluence titles must be "
                f"unique per space - change one H1.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        seen[sf.title] = sf.source


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError  # wired in a later task


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: all PASS. (Note: `stage_docs` already includes `docs/howto/confluence-sync.md` automatically once Task 9 creates it — the glob picks up every `*.md`.)

- [ ] **Step 5: Commit**

```bash
git add scripts/confluence-publish.py tests/test_confluence_publish.py
SQL_SYNC_SKIP=1 git commit -m "feat(docs-sync): staging, title preflight and index generation for Confluence publish"
```

---

### Task 4: Conversion smoke + golden invariants over the real corpus

This is the regression net for md2conf upgrades and the proof that all current docs convert. Uses md2conf's **local** mode (no network). If Task 1's spike found a different local-mode flag, use that name here.

**Files:**
- Modify: `tests/test_confluence_publish.py` (append)
- Modify: `scripts/confluence-publish.py` (add `convert_local`)

- [ ] **Step 1: Add `convert_local` to the driver**

Append to `scripts/confluence-publish.py` (after `preflight_titles`):

```python
def convert_local(stage_dir: Path) -> None:
    """Convert the staged tree to Confluence Storage Format locally (no API calls).

    Fails the run before anything touches Confluence if any document does not
    convert. Output files land next to the staged sources and are discarded
    with the stage.
    """
    cmd = [sys.executable, "-m", "md2conf", str(stage_dir), "--local", "--heading-anchors"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print("[publish] ERROR: local conversion failed:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(1)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_confluence_publish.py`:

```python
def _converted(stage: Path, staged_rel: str) -> str:
    """Return the locally-converted XML for one staged file."""
    # conversion output file extension: md2conf writes .csf next to sources
    # (verify against the Task 1 spike; adjust suffix if different)
    out = stage / staged_rel
    candidates = [out.with_suffix(".csf"), out.with_suffix(".xml")]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")
    raise AssertionError(f"no converted output for {staged_rel}: tried {candidates}")


@pytest.fixture(scope="session")
def converted_corpus(tmp_path_factory):
    stage = tmp_path_factory.mktemp("stage")
    cp.stage_docs(REPO_ROOT, stage)
    cp.convert_local(stage)
    return stage


class TestConversionGoldenInvariants:
    def test_whole_corpus_converts(self, converted_corpus):
        # convert_local raises SystemExit(1) on any failure; reaching here is the assertion
        assert converted_corpus.exists()

    def test_changelog_angle_brackets_escaped(self, converted_corpus):
        xml = _converted(converted_corpus, "CHANGELOG.md")
        # raw HTML tag names that appear as inline code in CHANGELOG must not
        # survive as live tags in storage XML
        assert "<thead>" not in xml
        assert "&lt;thead&gt;" in xml or "thead" in xml  # escaped or inside CDATA

    def test_changelog_mojibake_survives(self, converted_corpus):
        src = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        marker = "Generali â€"
        if marker in src:  # the intentional mojibake literal documenting the 0011 bug
            xml = _converted(converted_corpus, "CHANGELOG.md")
            assert marker in xml

    def test_nx_table_escaped_pipes(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/nx.md")
        # the '`int` \| `staging`' cell must render both words, not truncate at the pipe
        assert "int" in xml and "staging" in xml
        assert "<table" in xml

    def test_iis_ordered_list_survives_embedded_fence(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/iis.md")
        assert "<ol" in xml  # numbering not flattened by the in-list code fence

    def test_code_macro_emitted_for_powershell(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/ngrok.md")
        assert 'ac:name="code"' in xml

    def test_unicode_preserved(self, converted_corpus):
        xml = _converted(converted_corpus, "howto/babel.md")
        assert "→" in xml  # arrows in headings must not be mangled
```

- [ ] **Step 3: Run tests, fix only constants**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: PASS. If a failure is an output-extension or flag-name mismatch, fix the constant (in `_converted` / `convert_local`) per the Task 1 spike findings. If a failure is a real conversion defect (e.g. the escaped-pipe table truncates), STOP and record it — that's a finding to fix via doc edit or md2conf issue, not a test to weaken silently.

- [ ] **Step 4: Commit**

```bash
git add scripts/confluence-publish.py tests/test_confluence_publish.py
SQL_SYNC_SKIP=1 git commit -m "test(docs-sync): local-conversion smoke and golden invariants over the doc corpus"
```

---

### Task 5: Credentials loader + REST client with retry/backoff (TDD)

**Files:**
- Modify: `scripts/confluence-publish.py`
- Modify: `tests/test_confluence_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_confluence_publish.py`:

```python
from unittest import mock


class TestEnvFile:
    def test_parses_quoted_and_bare_values(self, tmp_path):
        f = tmp_path / "CONFLUENCE.env"
        f.write_text(
            '# comment\n'
            'CONFLUENCE_DOMAIN="sydocteam.atlassian.net"\n'
            "CONFLUENCE_USER_NAME=bot@sydoc.ch\n"
            'CONFLUENCE_API_KEY="s3cret"\n'
            'CONFLUENCE_SPACE_KEY="nexora"\n'
            "\n",
            encoding="utf-8",
        )
        env = cp.load_env_file(f)
        assert env["CONFLUENCE_DOMAIN"] == "sydocteam.atlassian.net"
        assert env["CONFLUENCE_USER_NAME"] == "bot@sydoc.ch"

    def test_missing_required_key_exits_2(self, tmp_path):
        f = tmp_path / "CONFLUENCE.env"
        f.write_text('CONFLUENCE_DOMAIN="x"\n', encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            cp.load_env_file(f)
        assert e.value.code == 2

    def test_missing_file_exits_2(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            cp.load_env_file(tmp_path / "nope.env")
        assert e.value.code == 2


def _resp(status=200, json_data=None, headers=None):
    r = mock.Mock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = json_data or {}
    r.raise_for_status.side_effect = None
    return r


def _client():
    return cp.ConfluenceClient("sydocteam.atlassian.net", "bot@sydoc.ch", "token")


class TestClientRetry:
    def test_retries_on_429_with_retry_after(self):
        c = _client()
        ok = _resp(200, {"ok": True})
        with mock.patch.object(
            c.session, "request", side_effect=[_resp(429, headers={"Retry-After": "0"}), ok]
        ) as req, mock.patch.object(cp.time, "sleep") as slept:
            out = c.request("GET", "/wiki/api/v2/spaces")
        assert out is ok
        assert req.call_count == 2
        slept.assert_called_once()

    def test_retries_on_500(self):
        c = _client()
        ok = _resp(200)
        with mock.patch.object(c.session, "request", side_effect=[_resp(500), ok]), mock.patch.object(
            cp.time, "sleep"
        ):
            assert c.request("GET", "/x") is ok

    def test_401_exits_2_with_rotation_hint(self, capsys):
        c = _client()
        with mock.patch.object(c.session, "request", return_value=_resp(401)):
            with pytest.raises(SystemExit) as e:
                c.request("GET", "/x")
        assert e.value.code == 2
        assert "token" in capsys.readouterr().err.lower()

    def test_gives_up_after_max_attempts(self):
        c = _client()
        with mock.patch.object(c.session, "request", return_value=_resp(429, headers={})), mock.patch.object(
            cp.time, "sleep"
        ):
            with pytest.raises(RuntimeError, match="attempts"):
                c.request("GET", "/x", max_attempts=3)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -k "EnvFile or ClientRetry" -v --no-cov
```

Expected: FAIL — `load_env_file` / `ConfluenceClient` not defined.

- [ ] **Step 3: Implement loader + client**

Append to `scripts/confluence-publish.py` (after `convert_local`; `requests` imported lazily because the staging/conversion path must work without it installed in odd envs):

```python
def load_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE env file (quotes optional, # comments ignored)."""
    if not path.exists():
        print(
            f"[publish] ERROR: credentials file not found: {path}\n"
            f"  Copy env/CONFLUENCE.env.example and fill in the bot token "
            f"(see docs/howto/confluence-sync.md).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in REQUIRED_ENV_KEYS if not env.get(k)]
    if missing:
        print(
            f"[publish] ERROR: {path} is missing required keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return env


class ConfluenceClient:
    """Minimal Confluence Cloud REST client: basic auth, 429/5xx retry, loud 401."""

    def __init__(self, domain: str, user: str, api_key: str) -> None:
        import requests  # lazy: only the publish path needs it

        self.base = f"https://{domain}"
        self.session = requests.Session()
        self.session.auth = (user, api_key)
        self.session.headers["Accept"] = "application/json"

    def request(self, method: str, path: str, *, max_attempts: int = 5, **kwargs):
        last_status = None
        for attempt in range(max_attempts):
            resp = self.session.request(method, self.base + path, timeout=60, **kwargs)
            last_status = resp.status_code
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = float(resp.headers.get("Retry-After") or 0)
                delay = retry_after or min(2**attempt + random.uniform(0, 1), 60)
                print(f"[publish]   {resp.status_code} on {method} {path}; retrying in {delay:.0f}s")
                time.sleep(delay)
                continue
            if resp.status_code in (401, 403):
                print(
                    f"[publish] ERROR: {resp.status_code} from Confluence - the API token is "
                    f"likely expired or revoked (Atlassian tokens expire after at most 365 "
                    f"days). Rotate it per docs/howto/confluence-sync.md.",
                    file=sys.stderr,
                )
                raise SystemExit(2)
            resp.raise_for_status()
            return resp
        raise RuntimeError(f"{method} {path}: still {last_status} after {max_attempts} attempts")
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/confluence-publish.py tests/test_confluence_publish.py
SQL_SYNC_SKIP=1 git commit -m "feat(docs-sync): credentials loader and Confluence REST client with retry"
```

---

### Task 6: Space/page/label/archive API methods + reconcile arithmetic (TDD)

**Files:**
- Modify: `scripts/confluence-publish.py`
- Modify: `tests/test_confluence_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_confluence_publish.py`:

```python
class TestReconcileArithmetic:
    HOMEPAGE = "323944774"

    def test_orphans_strays_and_homepage_exclusion(self):
        current = [
            {"id": "323944774", "title": "nexora"},  # homepage - never touched
            {"id": "1", "title": "Reporting"},  # published this run
            {"id": "2", "title": "Old synced doc"},  # owned, no longer published -> orphan
            {"id": "3", "title": "Random human page"},  # not owned -> stray
        ]
        owned = {"1", "2"}
        published_titles = {"Reporting"}
        orphans, strays = cp.compute_reconcile(current, owned, published_titles, self.HOMEPAGE)
        assert [p["id"] for p in orphans] == ["2"]
        assert [p["id"] for p in strays] == ["3"]

    def test_nothing_to_do(self):
        current = [{"id": "1", "title": "Reporting"}]
        orphans, strays = cp.compute_reconcile(current, {"1"}, {"Reporting"}, self.HOMEPAGE)
        assert orphans == [] and strays == []


class TestArchiveBatching:
    def test_batches_of_100_and_longtask_poll(self):
        c = _client()
        post = _resp(202, {"id": "task-1"})
        done = _resp(200, {"finished": True})
        with mock.patch.object(c, "request", side_effect=[post, done, post, done, post, done]) as req:
            c.archive_pages([str(i) for i in range(250)])
        posts = [k for k in req.call_args_list if k.args[0] == "POST"]
        assert len(posts) == 3
        sizes = [len(k.kwargs["json"]["pages"]) for k in posts]
        assert sizes == [100, 100, 50]


class TestSpaceLookup:
    def test_returns_space_and_homepage_id(self):
        c = _client()
        payload = {"results": [{"id": "111", "homepageId": "323944774", "key": "nexora"}]}
        with mock.patch.object(c, "request", return_value=_resp(200, payload)):
            space_id, homepage_id = c.get_space("nexora")
        assert (space_id, homepage_id) == ("111", "323944774")

    def test_missing_space_exits_2(self):
        c = _client()
        with mock.patch.object(c, "request", return_value=_resp(200, {"results": []})):
            with pytest.raises(SystemExit) as e:
                c.get_space("nexora")
        assert e.value.code == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -k "Reconcile or Archive or SpaceLookup" -v --no-cov
```

Expected: FAIL — methods not defined.

- [ ] **Step 3: Implement**

Append inside `ConfluenceClient`:

```python
    def get_space(self, space_key: str) -> tuple[str, str]:
        data = self.request("GET", f"/wiki/api/v2/spaces?keys={space_key}").json()
        results = data.get("results", [])
        if not results:
            print(f"[publish] ERROR: space '{space_key}' not found or not visible to the bot.", file=sys.stderr)
            raise SystemExit(2)
        space = results[0]
        return str(space["id"]), str(space["homepageId"])

    def list_current_pages(self, space_id: str) -> list[dict]:
        """All current (non-archived) pages in the space. v2 returns archived too unless filtered."""
        pages: list[dict] = []
        path = f"/wiki/api/v2/spaces/{space_id}/pages?status=current&limit=250"
        while path:
            data = self.request("GET", path).json()
            pages.extend({"id": str(p["id"]), "title": p["title"]} for p in data.get("results", []))
            path = data.get("_links", {}).get("next")  # relative /wiki/... path or absent
        return pages

    def pages_with_label(self, space_key: str, label: str) -> set[str]:
        """Page ids carrying the label, via v1 CQL search (v2 has no by-name label query)."""
        ids: set[str] = set()
        cql = f'space="{space_key}" AND type=page AND label="{label}"'
        path = f"/wiki/rest/api/search?cql={quote(cql)}&limit=100"
        while path:
            data = self.request("GET", path).json()
            for result in data.get("results", []):
                content = result.get("content") or {}
                if content.get("id"):
                    ids.add(str(content["id"]))
            path = data.get("_links", {}).get("next")
        return ids

    def find_page_id(self, space_id: str, title: str) -> str | None:
        data = self.request(
            "GET", f"/wiki/api/v2/pages?space-id={space_id}&title={quote(title)}&status=current"
        ).json()
        results = data.get("results", [])
        return str(results[0]["id"]) if results else None

    def add_label(self, page_id: str, label: str) -> None:
        self.request(
            "POST",
            f"/wiki/rest/api/content/{page_id}/label",
            json=[{"prefix": "global", "name": label}],
        )

    def archive_pages(self, page_ids: list[str]) -> None:
        """Bulk-archive via the v1 endpoint (no v2 equivalent). Async: poll the long task."""
        for start in range(0, len(page_ids), ARCHIVE_BATCH):
            batch = page_ids[start : start + ARCHIVE_BATCH]
            resp = self.request(
                "POST",
                "/wiki/rest/api/content/archive",
                json={"pages": [{"id": int(i)} for i in batch]},
            )
            task_id = resp.json().get("id")
            if task_id:
                self._wait_longtask(task_id)
            print(f"[publish]   archived {len(batch)} page(s)")

    def _wait_longtask(self, task_id: str, timeout_s: int = 300) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            data = self.request("GET", f"/wiki/rest/api/longtask/{task_id}").json()
            if data.get("finished"):
                return
            time.sleep(2)
        raise RuntimeError(f"archive long-task {task_id} did not finish within {timeout_s}s")
```

Add to the imports at the top of the file:

```python
from urllib.parse import quote
```

Append module-level (after `preflight_titles`):

```python
def compute_reconcile(
    current_pages: list[dict],
    owned_ids: set[str],
    published_titles: set[str],
    homepage_id: str,
) -> tuple[list[dict], list[dict]]:
    """Orphans = owned pages we no longer publish (archive). Strays = pages we never owned (warn)."""
    orphans: list[dict] = []
    strays: list[dict] = []
    for page in current_pages:
        if str(page["id"]) == str(homepage_id) or page["title"] in published_titles:
            continue
        (orphans if str(page["id"]) in owned_ids else strays).append(page)
    return orphans, strays
```

Note `_wait_longtask` polls with `self.request` — the mocked test feeds it `{"finished": True}` on the first poll, matching the `side_effect` ordering.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/confluence-publish.py tests/test_confluence_publish.py
SQL_SYNC_SKIP=1 git commit -m "feat(docs-sync): space lookup, labels, bulk archive and reconcile arithmetic"
```

---

### Task 7: `main()` wiring — flags, dry-run, bootstrap, publish, reconcile

**Files:**
- Modify: `scripts/confluence-publish.py` (replace the `main` stub)
- Modify: `tests/test_confluence_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_confluence_publish.py`:

```python
class TestMainDryRunWithoutCreds:
    def test_dry_run_local_only_when_no_env_file(self, tmp_path, capsys):
        rc = cp.main(["--dry-run", "--env-file", str(tmp_path / "absent.env"), "--stage-dir", str(tmp_path / "stage")])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "no credentials" in out.lower()
        # staged + converted, but never tried to reach Confluence
        assert (tmp_path / "stage" / "README.md").exists()


class TestArgParsing:
    def test_bootstrap_implies_confirmation_unless_yes(self):
        args = cp.parse_args(["--bootstrap"])
        assert args.bootstrap and not args.yes
        args = cp.parse_args(["--bootstrap", "--yes"])
        assert args.yes
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -k "Main or ArgParsing" -v --no-cov
```

Expected: FAIL (`parse_args` missing; `main` raises `NotImplementedError`).

- [ ] **Step 3: Implement `parse_args` and `main`**

Replace the `main` stub in `scripts/confluence-publish.py` with:

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish git-tracked docs to the nexora Confluence space (one-way mirror)."
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="first run: archive ALL existing non-homepage pages, then publish fresh",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompts")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"credentials file (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--stage-dir", type=Path, default=STAGE_DIR, help=argparse.SUPPRESS
    )  # test seam
    return parser.parse_args(argv)


def run_md2conf(stage_dir: Path, root_page_id: str, env: dict[str, str]) -> None:
    """Publish the staged tree under root_page_id. Banner + hierarchy + anchors.

    Flag names verified against md2conf 0.6.1 --help (Task 1 spike).
    """
    cmd = [
        sys.executable,
        "-m",
        "md2conf",
        str(stage_dir),
        "--root-page",
        root_page_id,
        "--keep-hierarchy",
        "--heading-anchors",
        "--generated-by",
        GENERATED_BY,
    ]
    merged = {**os.environ, **env, "CONFLUENCE_PATH": env.get("CONFLUENCE_PATH", "/wiki/")}
    result = subprocess.run(cmd, env=merged, cwd=REPO_ROOT)
    if result.returncode != 0:
        print("[publish] ERROR: md2conf publish failed (see output above).", file=sys.stderr)
        raise SystemExit(1)


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer == "y"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"[publish] staging publish set -> {args.stage_dir}")
    staged = stage_docs(REPO_ROOT, args.stage_dir)
    preflight_titles(staged)
    published_titles = {sf.title for sf in staged}
    for sf in sorted(staged, key=lambda s: str(s.staged)):
        print(f"  {sf.staged.relative_to(args.stage_dir)}  ->  '{sf.title}'")

    print("[publish] converting locally (validation)")
    convert_local(args.stage_dir)

    if args.dry_run and not args.env_file.exists():
        print("[publish] dry-run: no credentials file - skipping space preview.")
        print(f"[publish] done. staged={len(staged)} (dry-run, nothing published)")
        return 0

    env = load_env_file(args.env_file)
    client = ConfluenceClient(
        env["CONFLUENCE_DOMAIN"], env["CONFLUENCE_USER_NAME"], env["CONFLUENCE_API_KEY"]
    )
    space_id, homepage_id = client.get_space(env["CONFLUENCE_SPACE_KEY"])
    print(f"[publish] space '{env['CONFLUENCE_SPACE_KEY']}' id={space_id} homepage={homepage_id}")

    if args.bootstrap:
        pages = client.list_current_pages(space_id)
        to_archive = [p for p in pages if str(p["id"]) != homepage_id]
        print(f"[publish] BOOTSTRAP: {len(to_archive)} existing page(s) will be archived:")
        for p in to_archive:
            print(f"  archive: [{p['id']}] {p['title']}")
        if args.dry_run:
            print("[publish] done. (dry-run, nothing archived or published)")
            return 0
        if not confirm("Archive ALL pages above and republish from git?", args.yes):
            print("[publish] aborted.")
            return 1
        client.archive_pages([p["id"] for p in to_archive])

    if args.dry_run:
        current = client.list_current_pages(space_id)
        owned = client.pages_with_label(env["CONFLUENCE_SPACE_KEY"], OWNED_LABEL)
        orphans, strays = compute_reconcile(current, owned, published_titles, homepage_id)
        for p in orphans:
            print(f"  would archive: [{p['id']}] {p['title']}")
        for p in strays:
            print(f"  WARNING stray (untouched): [{p['id']}] {p['title']}")
        print(f"[publish] done. staged={len(staged)} would-archive={len(orphans)} (dry-run)")
        return 0

    print("[publish] publishing via md2conf")
    run_md2conf(args.stage_dir, homepage_id, env)

    print("[publish] labeling published pages")
    for title in sorted(published_titles):
        page_id = client.find_page_id(space_id, title)
        if page_id:
            client.add_label(page_id, OWNED_LABEL)
        else:
            print(f"[publish]   WARNING: published page not found by title: '{title}'")

    print("[publish] reconciling")
    current = client.list_current_pages(space_id)
    owned = client.pages_with_label(env["CONFLUENCE_SPACE_KEY"], OWNED_LABEL)
    orphans, strays = compute_reconcile(current, owned, published_titles, homepage_id)
    if orphans:
        for p in orphans:
            print(f"  archiving orphan: [{p['id']}] {p['title']}")
        client.archive_pages([p["id"] for p in orphans])
    for p in strays:
        print(f"  WARNING stray page (not owned by sync, left untouched): [{p['id']}] {p['title']}")

    print(
        f"[publish] done. published={len(published_titles)} archived={len(orphans)} "
        f"strays={len(strays)}"
    )
    return 0
```

- [ ] **Step 4: Run the full test file**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: all PASS.

- [ ] **Step 5: Lint (scripts/ isn't in CI's ruff scope, but keep it clean)**

```powershell
.\venv\Scripts\python.exe -m ruff check scripts/confluence-publish.py tests/test_confluence_publish.py
.\venv\Scripts\python.exe -m ruff format scripts/confluence-publish.py tests/test_confluence_publish.py
```

Expected: no findings (or auto-fixed formatting; re-run tests after).

- [ ] **Step 6: Commit**

```bash
git add scripts/confluence-publish.py tests/test_confluence_publish.py
SQL_SYNC_SKIP=1 git commit -m "feat(docs-sync): wire main() with dry-run, bootstrap, publish, label and reconcile"
```

---

### Task 8: CI workflow + credential template

**Files:**
- Create: `.github/workflows/confluence-docs.yml`
- Create: `env/CONFLUENCE.env.example`

- [ ] **Step 1: Create the workflow**

`.github/workflows/confluence-docs.yml`:

```yaml
name: Confluence docs sync

on:
  push:
    branches: [main]
    paths:
      - "docs/howto/**"
      - "docs/design/**"
      - "README.md"
      - "CONTRIBUTING.md"
      - "CHANGELOG.md"
      - "scripts/confluence-publish.py"
      - ".github/workflows/confluence-docs.yml"
  workflow_dispatch:

# Two syncs must never interleave (page-version races). Queue, don't cancel:
# the running sync finishes, the queued one then syncs the newest state.
concurrency:
  group: confluence-sync
  cancel-in-progress: false

jobs:
  publish:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4

      - name: Install Python deps
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          D:\sydoc\tools\py\python.exe -m pip install --quiet -r requirements-dev.txt

      - name: Copy CONFLUENCE.env into workspace env/
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          $src = "C:\sydoc\runner-secrets\CONFLUENCE.env"
          if (-not (Test-Path $src)) {
            throw "Runner is missing $src. Provision it once on the runner machine (see docs/howto/confluence-sync.md)."
          }
          Copy-Item $src "${{ github.workspace }}\env\CONFLUENCE.env" -Force

      - name: Publish docs to Confluence
        shell: powershell
        run: |
          $ErrorActionPreference = 'Stop'
          D:\sydoc\tools\py\python.exe scripts/confluence-publish.py --yes

      - name: Remove credentials copy
        if: always()
        shell: powershell
        run: |
          Remove-Item "${{ github.workspace }}\env\CONFLUENCE.env" -Force -ErrorAction SilentlyContinue
```

- [ ] **Step 2: Create the credential template**

`env/CONFLUENCE.env.example`:

```
# Confluence Cloud credentials for scripts/confluence-publish.py.
# Copy to env/CONFLUENCE.env (gitignored) and fill in.
# Bot account + UNSCOPED API token (basic auth at the site URL); tokens
# expire after at most 365 days - rotation runbook: docs/howto/confluence-sync.md
CONFLUENCE_DOMAIN="sydocteam.atlassian.net"
CONFLUENCE_PATH="/wiki/"
CONFLUENCE_USER_NAME="<bot-account-email>"
CONFLUENCE_API_KEY="<api-token>"
CONFLUENCE_SPACE_KEY="nexora"
```

- [ ] **Step 3: Verify ignore rules and YAML validity**

```powershell
git check-ignore -v env/CONFLUENCE.env          # must match the *.env rule
git status --short                               # CONFLUENCE.env.example shows as new; no .env file
.\venv\Scripts\python.exe -c "import yaml,sys; yaml.safe_load(open('.github/workflows/confluence-docs.yml')); print('yaml ok')"
```

Expected: ignore rule hits `.gitignore:172:*.env`; `yaml ok`. (If PyYAML isn't installed, skim-verify indentation manually instead — it is not worth adding a dep.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/confluence-docs.yml env/CONFLUENCE.env.example
SQL_SYNC_SKIP=1 git commit -m "ci(docs-sync): Confluence publish workflow and credential template"
```

---

### Task 9: Docs — runbook, CLAUDE.md, claude-workflow.md, CHANGELOG entry

**Files:**
- Create: `docs/howto/confluence-sync.md`
- Modify: `CLAUDE.md:5` and the "Keeping docs in sync" section
- Modify: `docs/howto/claude-workflow.md:97-105`
- Modify: `CHANGELOG.md` (`[Unreleased]` → `### Added`)

- [ ] **Step 1: Write the runbook**

`docs/howto/confluence-sync.md`:

```markdown
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

## Token rotation (yearly!)

Atlassian API tokens expire after at most 365 days. When the sync fails with
the 401 token message:

1. Log in as the bot account → <https://id.atlassian.com/manage-profile/security/api-tokens>
   → create a new (unscoped) token.
2. Update `C:\sydoc\runner-secrets\CONFLUENCE.env` on SYAPP01 (and your local
   `env/CONFLUENCE.env` if you run the script locally).
3. Re-run the workflow (*Actions → Confluence docs sync → Run workflow*).
4. Set a reminder for next year; revoke the old token.

## Bootstrap (already done — for reference / disaster recovery)

`--bootstrap` archives **all** existing non-homepage pages in the space (the
pre-sync hand-written docs were archived this way; recover any of them via
Confluence → Space settings → Archived pages), then publishes fresh from git.
After bootstrap, a space admin makes the space read-only for humans:
Space settings → Permissions → remove page add/edit/archive from user groups,
keep full write for the bot account only.

## Troubleshooting

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
```

- [ ] **Step 2: Update CLAUDE.md**

Replace line 5:

```markdown
Full product documentation lives in Confluence: https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774
```

with:

```markdown
Documentation is authored in git (`docs/`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`) and auto-published to Confluence (read-only mirror): https://sydocteam.atlassian.net/wiki/spaces/nexora/overview?homepageId=323944774 — see `docs/howto/confluence-sync.md`.
```

In the **"Keeping docs in sync"** section, append a bullet after the "Stale docs" bullet:

```markdown
- **Confluence:** `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md` are auto-published to the Confluence space on push to `main` (`.github/workflows/confluence-docs.yml`). Never edit those pages in Confluence — the sync overwrites them. Details: `docs/howto/confluence-sync.md`.
```

- [ ] **Step 3: Update docs/howto/claude-workflow.md**

In the "Confluence + Jira (official Atlassian MCP)" section (line ~97), replace the sentence

```markdown
nexora's product documentation lives in Confluence. The official remote MCP (GA Feb 2026, Claude launch partner) reads/writes Confluence + Jira over OAuth and respects your account's permissions:
```

with

```markdown
nexora's docs are authored in git and mirrored read-only to Confluence (see `docs/howto/confluence-sync.md`) — use the MCP for *reading* Confluence/Jira content that lives outside the mirrored docs. The official remote MCP (GA Feb 2026, Claude launch partner) reads/writes Confluence + Jira over OAuth and respects your account's permissions:
```

And add to its "See also" list (line ~111):

```markdown
- `docs/howto/confluence-sync.md` — git → Confluence docs mirror (publish set, token rotation)
```

- [ ] **Step 4: CHANGELOG entry**

Under `## [Unreleased]` → `### Added` (line 11), append:

```markdown
- Git → Confluence docs sync: `scripts/confluence-publish.py` publishes `docs/howto/*`, `docs/design/*`, `README.md`, `CONTRIBUTING.md` and `CHANGELOG.md` to the Confluence space as a read-only mirror (md2conf engine, `git-managed` labels, orphan archiving); triggered by `.github/workflows/confluence-docs.yml` on push to `main`. Runbook: `docs/howto/confluence-sync.md`.
```

- [ ] **Step 5: Re-run the corpus tests (the runbook is now part of the corpus)**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_confluence_publish.py -v --no-cov
```

Expected: PASS — `stage_docs` picks up `docs/howto/confluence-sync.md` via the glob; its H1 "Confluence docs sync" is unique.

- [ ] **Step 6: Commit**

```bash
git add docs/howto/confluence-sync.md CLAUDE.md docs/howto/claude-workflow.md CHANGELOG.md
SQL_SYNC_SKIP=1 git commit -m "docs(docs-sync): runbook, CLAUDE.md and workflow-doc updates for the Confluence mirror"
```

---

### Task 10: Live verification — pilot, bootstrap, permission flip (manual, owner-gated)

**Prerequisites (owner, manual):** bot account created; unscoped API token minted; tenant plan is Standard+ (archiving available); `env/CONFLUENCE.env` filled locally; `C:\sydoc\runner-secrets\CONFLUENCE.env` provisioned on SYAPP01.

- [ ] **Step 1: Pilot against a scratch page (validates md2conf behavior before touching real content)**

Manually create a page titled `Sync pilot` anywhere in the space, note its id from the URL. Then:

```powershell
mkdir var\pilot-stage; copy docs\howto\ngrok.md var\pilot-stage\
$env:CONFLUENCE_DOMAIN="sydocteam.atlassian.net"; $env:CONFLUENCE_PATH="/wiki/"
$env:CONFLUENCE_USER_NAME="<bot email>"; $env:CONFLUENCE_API_KEY="<token>"; $env:CONFLUENCE_SPACE_KEY="nexora"
.\venv\Scripts\python.exe -m md2conf var\pilot-stage --root-page <PILOT_PAGE_ID> --keep-hierarchy --heading-anchors --generated-by "pilot banner test"
```

Verify in the browser: child page "ngrok setup (SYAPP01)" exists under the pilot page, banner shows, code block renders. **Re-run the same command** — expected: output reports the page as up-to-date and the page version in Confluence did NOT increment (this is the idempotency guarantee). Then check whether the *root* pilot page's body was overwritten by anything (it has no README.md staged — body should be untouched; record what happens for the homepage question). Afterwards clear `$env:CONFLUENCE_*` vars (`Remove-Item env:CONFLUENCE_DOMAIN` etc.), delete the pilot page and `var\pilot-stage`.

If `--root-page`/`--keep-hierarchy` behave differently than assumed (e.g. README.md at stage root does NOT become the root-page body when later tested), implement the spec's fallback: after `run_md2conf`, the driver PUTs the converted README body onto the homepage via `PUT /wiki/api/v2/pages/{homepage_id}` (read current version first, send `version.number = current + 1`).

- [ ] **Step 2: Full dry-run from the dev box**

```powershell
.\venv\Scripts\python.exe scripts\confluence-publish.py --dry-run
```

Expected: lists 14 staged pages (README, CONTRIBUTING, CHANGELOG, 8× howto incl. the new runbook, 1× design, 2× generated indexes — verify the printed `staged=N` matches), prints existing pages as `WARNING stray` (nothing labeled yet), archives nothing.

- [ ] **Step 3: Bootstrap (the moment the old space content is archived)**

```powershell
.\venv\Scripts\python.exe scripts\confluence-publish.py --bootstrap --dry-run   # review the archive list!
.\venv\Scripts\python.exe scripts\confluence-publish.py --bootstrap             # answer y
```

Expected: old pages archived (recoverable via Space settings → Archived pages), full tree published per the spec's §5 diagram. Eyeball in the browser: homepage body, "How-to guides" index links resolve to sibling pages, `Reporting` (the largest page) renders without macro errors, `nx — the nexora dev CLI` tables show the escaped-pipe cells correctly, every page shows the banner.

- [ ] **Step 4: Idempotency + steady-state checks**

```powershell
.\venv\Scripts\python.exe scripts\confluence-publish.py --yes
```

Expected: zero page updates ("up-to-date" for every page), `archived=0`. Then test the mirror semantics end-to-end on a throwaway branch merged to... no — do NOT test via main; instead locally: temporarily rename `docs/howto/ngrok.md` H1 to `# ngrok setup (SYAPP01) v2`, run `--dry-run` (expected: new title staged, old "ngrok setup (SYAPP01)" listed as would-archive), then `git checkout -- docs/howto/ngrok.md` to revert.

- [ ] **Step 5: Flip the space read-only + verify CI**

Space settings → Permissions: remove page add/edit/archive from all human groups; bot keeps full write (exact clicks in the runbook). Then merge the feature branch to `main` (owner does push/PR per repo workflow) and watch *Actions → Confluence docs sync*: green run, only changed pages touched.

- [ ] **Step 6: Record the completion**

Add the go-live date + bot account name (not the token!) to `docs/howto/confluence-sync.md` under the Bootstrap section, commit via the normal docs flow (which now syncs itself — pleasing).

---

## Self-review notes (spec → plan coverage)

- Spec §2 scope table → Task 3 `ROOT_FILES`/`DIR_MAP`; superpowers/releases excluded by construction (explicit dir map, no recursive glob).
- Spec §3 tooling + archive endpoint constraints → Tasks 1, 6 (v1 archive, batches ≤100, longtask poll, `status=current` filter).
- Spec §4.1 phase ordering → `main()` order in Task 7: stage → preflight → convert-local → (bootstrap) → publish → label → reconcile.
- Spec §4.1 flags table → Task 7 `parse_args` (`--dry-run`, `--bootstrap`, `--yes`, `--env-file`).
- Spec §4.1 error handling (429/5xx retry, 401 loud, stale-version) → Task 5; stale-version retry is md2conf's job during publish (it re-reads versions itself); the driver's own writes (labels, archive, properties) are create-style calls without version races.
- Spec §4.2 credentials → Tasks 5, 8 (`env/CONFLUENCE.env` + example + runner-secrets copy step).
- Spec §4.3 workflow → Task 8 (path filter, concurrency group, runner-secrets pattern, cleanup step).
- Spec §4.4 deps → Task 1 (dev extra, both exports checked).
- Spec §4.5 tests → Tasks 3-7 (staging, titles, golden invariants incl. mojibake/pipes/lists, reconcile arithmetic, batching, retries, env parsing, dry-run path).
- Spec §4.6 runbook → Task 9; §5 tree + §6 read-only flip + §9 rollout → Task 10.
- Spec §8 risks: token rotation (Task 5 message + Task 9 runbook), md2conf pin (Task 1), half-update recovery (idempotent re-run, Task 7 ordering), trash-title-hostage (runbook), homepage-archive guard (`compute_reconcile` + bootstrap filter, tested in Task 6).
- Known open verification: md2conf root-page README behavior (spec §4.1 fallback) — explicitly carried in Task 10 Step 1.
