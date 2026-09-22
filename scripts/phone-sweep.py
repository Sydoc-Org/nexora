r"""Sweep the phone layout across real iPhone geometries and both engines.

Why this exists
---------------
Three phone symptoms reported from a real iPhone could not be reproduced on
this machine at all. Two blind spots explain that, and this script closes
both:

  1. **Safe-area insets read 0 in every emulator.** `env(safe-area-inset-*)`
     cannot be overridden, so a desktop browser reports no notch and no home
     indicator while a real iPhone reports ~59px top and ~34px bottom. Any
     layout error in that band was structurally invisible. The app now reads
     those insets through `--nx-sa-*` tokens (see the token block in
     `static/css/nexora-ui.css`), and a custom property *can* be set -- so
     this script injects each device's true values before measuring.

  2. **Chromium is not Safari.** Text metrics differ, so a row that fits by a
     few pixels here can overflow there. Playwright's WebKit is Safari's
     engine, and running both is the only way to catch it. Install it once
     with `python -m playwright install webkit`. It earns its keep: the
     reporting page overflows by 53px in WebKit at every width and by 0 in
     Chromium.

And one habit worth keeping: **measure more than one width.** Every number in
the original phone effort was taken at 390x844, which is how a toolbar that
was draggable at 375 shipped looking fine.

Usage
-----
Start the dev server first (`nx -u`), then::

    ./.venv/Scripts/python.exe scripts/phone-sweep.py
    ./.venv/Scripts/python.exe scripts/phone-sweep.py --pages /reporting,/dashboard
    ./.venv/Scripts/python.exe scripts/phone-sweep.py --engine webkit --user mara.mihajlovic

Writes `var/phone-sweep.json` with the full detail and prints a summary. It
is read-only against the app -- it logs in through the loopback-only
`/dev/login/<user>` route and never submits a form.

**In Git Bash, prefix the command with `MSYS_NO_PATHCONV=1`.** MSYS rewrites
any argument that looks like a POSIX path, so `--pages /reporting` arrives as
`C:/Users/.../Git/reporting` and every load fails with "Cannot navigate to
invalid URL". PowerShell needs no such prefix.

What it looks for
-----------------
Each detector maps to something a person actually reported seeing:

  ``sideways``   the page can be dragged left/right -- "the page is too big,
                 some css is off"
  ``clipped``    a box whose content is taller than it is, with `overflow-y:
                 hidden`, so the rest is unreachable -- "it gets cut off half
                 way"
  ``scrollers``  an inner box that scrolls sideways under the finger while
                 the page stays put -- "the middle content flies around but
                 the page doesn't"
  ``tiny``       tap targets under Apple's 44px minimum

A note on reading the output: an element flagged by ``sideways`` is often a
*symptom*, not the cause. A `position: fixed` bar stretches to the scrollable
width, so the tab bar shows up 37px too wide on a page whose real problem is
a grid item that refuses to shrink. Work from the innermost static element
outwards, and prefer the ``wide`` list -- a box whose own content overflows
it with `overflow-x: visible` is what actually pushes the document wider.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# width, height, safe-area top, safe-area bottom -- the real values per device.
# The SE is in the list precisely because it has no notch: it is the one phone
# where the insets are nearly zero, so a layout that only works *because* of
# the inset padding fails there and nowhere else.
DEVICES = [
    ("iPhone SE 3", 375, 667, 20, 0),
    ("iPhone 13 mini", 375, 812, 50, 34),
    ("iPhone 14", 390, 844, 47, 34),
    ("iPhone 16", 393, 852, 59, 34),
    ("iPhone 16 Pro", 402, 874, 59, 34),
    ("iPhone 11", 414, 896, 48, 34),
    ("iPhone 16 Pro Max", 430, 932, 59, 34),
]

DEFAULT_PAGES = ["/dashboard", "/reporting", "/workitems", "/profile", "/appearance"]

# Injecting the device's true insets is the whole point of the --nx-sa-* tokens.
# An inline style on <html> outranks the :root rule, so this wins without
# touching the stylesheet.
FAKE_INSETS = """([top, bottom]) => {
  const root = document.documentElement.style;
  root.setProperty('--nx-sa-top', top + 'px');
  root.setProperty('--nx-sa-bottom', bottom + 'px');
}"""

PROBE = r"""() => {
  const out = {sideways: null, scrollers: [], clipped: [], tiny: [], wide: []};
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1)
    out.sideways = {over: de.scrollWidth - de.clientWidth,
                    scrollWidth: de.scrollWidth, clientWidth: de.clientWidth};

  const path = el => {
    const parts = []; let e = el;
    while (e && e.tagName && parts.length < 4) {
      let s = e.tagName.toLowerCase();
      if (e.id) { parts.unshift(s + '#' + e.id); break; }
      if (e.className && typeof e.className === 'string')
        s += '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.');
      parts.unshift(s); e = e.parentElement;
    }
    return parts.join(' > ');
  };
  const shown = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };

  for (const el of document.querySelectorAll('*')) {
    if (!shown(el)) continue;
    const cs = getComputedStyle(el);
    const overX = el.scrollWidth - el.clientWidth;
    const overY = el.scrollHeight - el.clientHeight;

    // Scrolls sideways under the finger while the page stays put.
    if (overX > 2 && ['auto', 'scroll'].includes(cs.overflowX) && el.clientWidth > 40)
      out.scrollers.push({sel: path(el), over: overX, w: Math.round(el.clientWidth)});

    // Content wider than its box that is NOT clipped -- this is what pushes
    // the document wider, and it is invisible to a rect-based check because
    // the box itself still measures inside the viewport.
    if (overX > 2 && cs.overflowX === 'visible' && el.clientWidth > 0)
      out.wide.push({sel: path(el), over: overX, cw: el.clientWidth});

    // Taller than its box with no way to reach the rest.
    if (overY > 4 && cs.overflowY === 'hidden' && el.clientHeight > 40)
      out.clipped.push({sel: path(el), lost: overY, h: Math.round(el.clientHeight)});
  }

  for (const el of document.querySelectorAll(
        'a,button,input,select,textarea,[role=button],[onclick]')) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 44 || r.height < 44)
      out.tiny.push({sel: path(el), w: Math.round(r.width), h: Math.round(r.height)});
  }
  out.wide.sort((a, b) => b.over - a.over);
  out.wide = out.wide.slice(0, 12);
  return out;
}"""


def sweep(base: str, user: str, pages: list[str], engines: list[str]) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - dev tooling
        sys.exit("playwright is not installed -- run `uv sync`")

    findings: list[dict] = []
    with sync_playwright() as pw:
        for engine in engines:
            try:
                browser = getattr(pw, engine).launch()
            except Exception as exc:  # pragma: no cover - dev tooling
                print(
                    f"  ! {engine} unavailable ({exc}). "
                    f"Install it with `python -m playwright install {engine}`."
                )
                continue
            print(f"\n== {engine} " + "=" * 56)
            for name, w, h, sa_top, sa_bottom in DEVICES:
                ctx = browser.new_context(
                    viewport={"width": w, "height": h}, has_touch=True, is_mobile=True
                )
                page = ctx.new_page()
                page.goto(f"{base}/dev/login/{user}", wait_until="domcontentloaded")
                for path in pages:
                    row = {
                        "engine": engine,
                        "device": name,
                        "w": w,
                        "h": h,
                        "sa_top": sa_top,
                        "sa_bottom": sa_bottom,
                        "page": path,
                    }
                    try:
                        # `load` rather than `networkidle`: the workitems page
                        # keeps a request open and never goes idle, which read
                        # as a failure the first time this ran.
                        page.goto(base + path, wait_until="load", timeout=30000)
                        page.evaluate(FAKE_INSETS, [sa_top, sa_bottom])
                        page.wait_for_timeout(500)
                        row.update(page.evaluate(PROBE))
                    except Exception as exc:
                        row["error"] = str(exc).splitlines()[0][:120]
                    findings.append(row)
                    flag = (
                        "OVER " + str(row["sideways"]["over"]) if row.get("sideways") else "  -  "
                    )
                    print(
                        f"  {name:18} {path:12} side={flag:9} "
                        f"slide={len(row.get('scrollers', [])):<3} "
                        f"clip={len(row.get('clipped', [])):<3} "
                        f"tiny={len(row.get('tiny', [])):<3}"
                        + ("  ERROR" if "error" in row else ""),
                        flush=True,
                    )
                ctx.close()
            browser.close()
    return findings


def summarise(findings: list[dict]) -> None:
    print("\n" + "=" * 68)
    sideways: dict[tuple[str, str], list] = {}
    for row in findings:
        if row.get("sideways"):
            sideways.setdefault((row["page"], row["engine"]), []).append(
                (row["w"], row["device"], row["sideways"]["over"])
            )
    if sideways:
        print("\nPAGE SCROLLS SIDEWAYS")
        for (page, engine), hits in sorted(sideways.items()):
            overs = sorted({o for _, _, o in hits})
            print(f"  {page:12} {engine:9} {len(hits)}/{len(DEVICES)} devices, over by {overs}px")
            worst = max(hits, key=lambda x: x[2])
            for row in findings:
                if (row["page"], row["engine"]) == (page, engine) and row["w"] == worst[0]:
                    for item in row.get("wide", [])[:4]:
                        print(
                            f"      content +{item['over']:<4} in a {item['cw']}px box: {item['sel'][:62]}"
                        )
                    break
    clipped = [(r, c) for r in findings for c in r.get("clipped", [])]
    if clipped:
        print("\nCONTENT CUT OFF")
        seen = set()
        for row, c in clipped:
            key = (row["page"], c["sel"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  {row['page']:12} {row['engine']:9} {c['sel'][:50]:52} loses {c['lost']}px")
    slide = [(r, s) for r in findings for s in r.get("scrollers", [])]
    if slide:
        print("\nINNER BOX SLIDES SIDEWAYS")
        seen = set()
        for row, s in slide:
            key = (row["page"], s["sel"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  {row['page']:12} {row['engine']:9} {s['sel'][:50]:52} +{s['over']}px")
    worst_tiny: dict[str, int] = {}
    for row in findings:
        n = len(row.get("tiny", []))
        if n > worst_tiny.get(row["page"], 0):
            worst_tiny[row["page"]] = n
    if any(worst_tiny.values()):
        print("\nTAP TARGETS UNDER 44px (worst device per page)")
        for page, n in sorted(worst_tiny.items(), key=lambda kv: -kv[1]):
            if n:
                print(f"  {page:12} {n}")
    errors = [r for r in findings if "error" in r]
    if errors:
        print(f"\nCOULD NOT LOAD ({len(errors)})")
        for r in errors[:6]:
            print(f"  {r['engine']:9} {r['device']:18} {r['page']:12} {r['error'][:70]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--base", default="http://127.0.0.1:8000", help="dev server root (default: %(default)s)"
    )
    ap.add_argument(
        "--user", default="ben.streich", help="INT username for /dev/login (default: %(default)s)"
    )
    ap.add_argument(
        "--pages", default=",".join(DEFAULT_PAGES), help="comma-separated paths to sweep"
    )
    ap.add_argument(
        "--engine",
        default="chromium,webkit",
        help="comma-separated: chromium, webkit (default: both)",
    )
    ap.add_argument("--out", default="var/phone-sweep.json")
    args = ap.parse_args()

    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    engines = [e.strip() for e in args.engine.split(",") if e.strip()]
    findings = sweep(args.base, args.user, pages, engines)

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, indent=1), encoding="utf-8")
    summarise(findings)
    print(f"\n{len(findings)} page-runs -> {args.out}")


if __name__ == "__main__":
    main()
