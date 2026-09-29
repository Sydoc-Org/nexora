#!/usr/bin/env python
"""Capture one screenshot per page-gating permission, for the permission
detail page (``/admin/permissions/detail/<code>``).

A permission's route and its grant state are derived at request time
(``nx_lib/permission_docs.py``), but "what does the holder actually see" is not
derivable -- so it is captured here and committed under
``static/img/permissions/``. Only codes that gate a linkable page get one: a
GET rule with no URL arguments that is not under ``/api/``. Everything else
shows its routes and its UI hooks and no image, which is correct -- there is no
single screen behind ``reporting.export``.

These are JPEGs, not PNGs: the whole set is shipped to every environment by the
``robocopy /MIR`` deploy, and quality 72 at 1100px costs about a tenth of the
PNG for a difference nobody reading a thumbnail can see.

Re-run it after a UI change; the images drift the way any screenshot does, and
nothing detects that for you.

    .venv/Scripts/python scripts/capture-permission-shots.py --user ben.streich

Needs a nexora running locally (``nx -u``) whose ``/dev/login/<user>`` is
reachable -- the capture user must hold the permissions, or the pages it opens
are 403 error screens.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "static" / "img" / "permissions"
# Wide enough that the real layout renders (the admin grids collapse below
# ~1100), short enough that the image reads as a thumbnail beside the page.
VIEWPORT = {"width": 1100, "height": 760}
QUALITY = 72


def page_routes() -> dict[str, str]:
    """code -> the one page route to shoot for it."""
    from nx_lib import permission_docs
    from nx_main import app

    index = permission_docs.routes_index(app.url_map, app.view_functions)
    out = {}
    for code, routes in index.items():
        pages = [r["rule"] for r in routes if r["page"]]
        if pages:
            out[code] = pages[0]
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="running nexora")
    ap.add_argument("--user", default="ben.streich", help="username for /dev/login")
    ap.add_argument("--only", help="capture just this permission code")
    ap.add_argument("--clean", action="store_true", help="delete existing shots first")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed in this environment", file=sys.stderr)
        return 2

    targets = page_routes()
    if args.only:
        if args.only not in targets:
            print(f"{args.only} does not gate a linkable page", file=sys.stderr)
            return 1
        targets = {args.only: targets[args.only]}

    if args.clean and OUT_DIR.is_dir():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written, skipped = 0, []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        login = page.goto(f"{args.base}/dev/login/{args.user}", wait_until="domcontentloaded")
        if login is None or login.status >= 400:
            print(f"cannot log in as {args.user} at {args.base}", file=sys.stderr)
            browser.close()
            return 1

        for code, rule in targets.items():
            resp = page.goto(f"{args.base}{rule}", wait_until="domcontentloaded")
            page.wait_for_timeout(1200)  # let the client-side tables paint
            status = resp.status if resp else 0
            if status != 200:
                # A 403 here means the capture user lacks the permission: an
                # error page is worse than no picture, so keep no picture.
                skipped.append((code, rule, status))
                continue
            page.mouse.move(VIEWPORT["width"] - 8, VIEWPORT["height"] - 8)
            page.screenshot(path=OUT_DIR / f"{code}.jpg", type="jpeg", quality=QUALITY)
            written += 1
            print(f"  {code:42} {rule}")
        browser.close()

    total = sum(f.stat().st_size for f in OUT_DIR.glob("*.jpg"))
    print(f"\n{written} captured, {total / 1024:.0f} KB total in {OUT_DIR.relative_to(ROOT)}")
    for code, rule, status in skipped:
        print(f"  skipped {code} ({rule}): HTTP {status}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
