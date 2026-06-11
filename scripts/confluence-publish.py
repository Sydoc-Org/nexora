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
from urllib.parse import quote

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


def convert_local(stage_dir: Path) -> None:
    """Convert the staged tree to Confluence Storage Format locally (no API calls).

    Fails the run before anything touches Confluence if any document does not
    convert. Output files land next to the staged sources and are discarded
    with the stage.
    """
    cmd = [
        sys.executable,
        "-m",
        "md2conf",
        str(stage_dir),
        "--local",
        "--heading-anchors",
        "--domain",
        "dummy.atlassian.net",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.returncode != 0:
        print("[publish] ERROR: local conversion failed:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(1)


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
                print(
                    f"[publish]   {resp.status_code} on {method} {path}; "
                    f"retrying in {delay:.0f}s"
                )
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

    def get_space(self, space_key: str) -> tuple[str, str]:
        data = self.request("GET", f"/wiki/api/v2/spaces?keys={space_key}").json()
        results = data.get("results", [])
        if not results:
            print(
                f"[publish] ERROR: space '{space_key}' not found or not visible to the bot.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        space = results[0]
        return str(space["id"]), str(space["homepageId"])

    def list_current_pages(self, space_id: str) -> list[dict]:
        """All current (non-archived) pages in the space."""
        pages: list[dict] = []
        path = f"/wiki/api/v2/spaces/{space_id}/pages?status=current&limit=250"
        while path:
            data = self.request("GET", path).json()
            pages.extend({"id": str(p["id"]), "title": p["title"]} for p in data.get("results", []))
            path = data.get("_links", {}).get("next")
        return pages

    def pages_with_label(self, space_key: str, label: str) -> set[str]:
        """Page ids carrying the label, via v1 CQL search."""
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
            "GET",
            f"/wiki/api/v2/pages?space-id={space_id}&title={quote(title)}&status=current",
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
        """Bulk-archive via the v1 endpoint. Async: polls the long task."""
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
    parser.add_argument("--stage-dir", type=Path, default=STAGE_DIR, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def run_md2conf(stage_dir: Path, root_page_id: str, env: dict[str, str]) -> None:
    """Publish the staged tree under root_page_id.

    Flag names verified against md2conf 0.6.1 --help (Task 1 spike).
    --skip-update: stage dir is ephemeral per run; don't inject page IDs back.
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
        "--skip-update",
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


if __name__ == "__main__":
    sys.exit(main())
