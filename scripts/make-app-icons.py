"""Render the nexora black-hole mark to the static PNG app icons (#354).

Home-screen and taskbar icons cannot animate -- iOS and Android both take a
still image -- so the animated CSS mark has to be frozen into one frame. The
mark is drawn entirely in CSS (`static/css/_nexoraLogo.css`: gradients,
border-radius, a rotating accretion disk), so there is no source image to
export from. This renders the real element in a real browser instead, which
keeps the icon honest: change the CSS and re-run this, rather than hand-editing
a PNG that then silently drifts from the logo everyone sees in the sidebar.

The disk animation is paused at a fixed negative delay so the frame is
deterministic -- re-running gives byte-identical output instead of whatever
rotation the browser happened to be on.

Usage (needs the dev server up for the stylesheet, default http://localhost:8123):

    .venv/Scripts/python.exe scripts/make-app-icons.py [--base-url URL]

Writes static/images/icon-{180,192,512}.png and icon-maskable-512.png.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "static" / "images"

# The app's dark chrome. An icon needs an opaque background -- iOS composites a
# transparent PNG onto black and Android onto the launcher's own colour, so
# either way "transparent" means "unpredictable".
BG = "#0f172a"

# Logical size of the .bh element, then the DPI multiplier we render at. 60 *
# 16 = 960px of real pixels to downsample from, which keeps the gradients and
# the ring edge clean at 512.
BH_PX = 60
SCALE = 16

# Frozen mid-rotation. Any fixed value works; this one shows the disk at an
# angle rather than square-on.
FREEZE_DELAY = "-6s"

PAGE = """
<!doctype html>
<html><head>
<link rel="stylesheet" href="{base}/static/css/_nexoraLogo.css">
<style>
  html, body {{ margin: 0; padding: 0; background: {bg}; }}
  /* A little air around the mark so the disk's glow is not clipped. */
  #stage {{
    width: {stage}px; height: {stage}px;
    background: {bg};
    display: flex; align-items: center; justify-content: center;
  }}
  /* Freeze every animation on a fixed frame so re-runs are identical. */
  #stage *, #stage *::before, #stage *::after {{
    animation-play-state: paused !important;
    animation-delay: {delay} !important;
  }}
</style>
</head><body>
  <div id="stage">
    <div class="bh" aria-hidden="true">
      <div class="bh-penumbra" aria-hidden="true"></div>
      <div class="bh-core"></div>
      <div class="bh-einstein-ring"></div>
      <div class="bh-disk"></div>
      <div class="bh-sparks" aria-hidden="true"><i></i><i></i></div>
    </div>
  </div>
</body></html>
"""


def render(base_url: str) -> Image.Image:
    stage = int(BH_PX * 1.32)  # the disk spans wider than .bh -- keep its ends inside the frame
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": stage, "height": stage},
            device_scale_factor=SCALE,
        )
        page.set_content(PAGE.format(base=base_url, bg=BG, stage=stage, delay=FREEZE_DELAY))
        # The stylesheet is fetched over HTTP; wait for it before shooting.
        page.wait_for_load_state("load")
        page.wait_for_timeout(400)
        shot = OUT / "_icon-raw.png"
        page.locator("#stage").screenshot(path=str(shot))
        browser.close()
    img = Image.open(shot).convert("RGB")
    shot.unlink()
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8123")
    args = ap.parse_args()

    img = render(args.base_url)
    print(f"rendered {img.size[0]}x{img.size[1]}")

    # Plain icons: the mark filling the square, for contexts that draw the icon
    # as-is (iOS home screen, Windows taskbar).
    for size in (512, 192, 180):
        out = OUT / f"icon-{size}.png"
        img.resize((size, size), Image.LANCZOS).save(out, "PNG", optimize=True)
        print(f"wrote {out.relative_to(REPO)}")

    # Maskable: Android crops icons to whatever shape the launcher uses (circle,
    # squircle, rounded square), so the mark has to sit inside the safe zone --
    # the middle 80% -- or the launcher shaves its edges off.
    side = 512
    safe = int(side * 0.8)
    canvas = Image.new("RGB", (side, side), BG)
    mark = img.resize((safe, safe), Image.LANCZOS)
    off = (side - safe) // 2
    canvas.paste(mark, (off, off))
    out = OUT / "icon-maskable-512.png"
    canvas.save(out, "PNG", optimize=True)
    print(f"wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
