"""Template lint: elements hidden via the Tailwind `[display:none]!` class
must not be un-hidden through inline styles.

`[display:none]!` compiles to `display:none !important`, which an inline
`el.style.display = ''` (or 'block'/'flex'/...) can never override — the
element stays invisible forever. That exact seam broke the Generali user
filter on five pages after the #142 inline-style cleanup (client-reported
2026-08). Show/hide such elements with
`el.classList.remove/add/toggle('[display:none]!')` instead.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"

TAG_RE = re.compile(r"<[^>]*\[display:none\]![^>]*>")
ID_RE = re.compile(r'\bid="([^"]+)"')


def _important_hidden_ids():
    ids = set()
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        for tag in TAG_RE.findall(tpl.read_text(encoding="utf-8", errors="replace")):
            m = ID_RE.search(tag)
            if m:
                ids.add(m.group(1))
    return ids


def test_no_inline_style_unhide_of_important_hidden_ids():
    offenders = []
    for hid in sorted(_important_hidden_ids()):
        # direct chain: getElementById('X').style.display = <rhs>
        direct = re.compile(
            r"getElementById\(['\"]" + re.escape(hid) + r"['\"]\)\s*"
            r"(?:\.style\.display\s*=\s*(?P<rhs>[^;\n]+))"
        )
        # alias: const y = document.getElementById('X') ... y.style.display = <rhs>
        alias_decl = re.compile(
            r"(\w+)\s*=\s*document\.getElementById\(['\"]" + re.escape(hid) + r"['\"]\)"
        )
        for tpl in sorted(TEMPLATES.rglob("*.html")):
            text = tpl.read_text(encoding="utf-8", errors="replace")
            rhss = [m.group("rhs") for m in direct.finditer(text)]
            for am in alias_decl.finditer(text):
                alias_use = re.compile(
                    re.escape(am.group(1)) + r"\.style\.display\s*=\s*(?P<rhs>[^;\n]+)"
                )
                rhss += [m.group("rhs") for m in alias_use.finditer(text)]
            for rhs in rhss:
                # assigning only 'none' is harmless; anything that can show is not
                if rhs.strip() in ("'none'", '"none"'):
                    continue
                offenders.append(
                    f"{tpl.relative_to(REPO_ROOT)}: #{hid} <- .style.display = {rhs.strip()}"
                )
    assert not offenders, (
        "Inline-style unhide of a [display:none]! element (display:none !important "
        "always wins — use classList.remove/toggle('[display:none]!')):\n" + "\n".join(offenders)
    )
