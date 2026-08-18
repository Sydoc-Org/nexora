"""Template lint: no inline on<event>= attribute handlers (#193 finding 10).

The PROD CSP has no 'unsafe-inline' in script-src and a script-src nonce does
not cover attribute handlers, so any onclick=""/onchange=""/... in a template
is silently refused by the browser on PROD — while dev/INT, where Talisman is
off, keep working. That asymmetry shipped v3.1 with dead Generali edit/delete
row buttons on four pages. Wire handlers with addEventListener (or delegation)
instead; this test fails on any inline handler that sneaks back in.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"

# An on<event>= followed by a quote/backtick — matches HTML attributes and
# attributes built inside JS template literals, but not `window.onclick = fn`.
HANDLER = re.compile(
    r"""\bon(click|dblclick|change|submit|input|load|error|keyup|keydown|keypress|"""
    r"""mouseover|mouseout|mousedown|mouseup|mouseenter|mouseleave|blur|focus)\s*=\s*["'`]"""
)


def test_no_inline_event_handlers():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        if "archive" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            # ponytail: line-based comment skip — enough for the /* … */ and
            # {# … #} styles actually used in these templates.
            if stripped.startswith(("//", "*", "/*", "{#", "<!--")):
                continue
            if HANDLER.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{lineno}: {stripped[:120]}")
    assert not offenders, (
        "Inline on<event>= handlers are refused by the PROD CSP (script-src has no "
        "'unsafe-inline'); use addEventListener/delegation instead:\n" + "\n".join(offenders)
    )
