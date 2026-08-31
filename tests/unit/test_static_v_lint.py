"""Template lint: static assets go through static_v(), not raw url_for('static').

nx_lib/__init__.py sets SEND_FILE_MAX_AGE_DEFAULT to a year (#191 follow-up,
task 5) on the assumption that every asset URL in a template carries the
static_v() ?v=<mtime> cache-buster. A raw url_for('static', filename=...)
call has no cache-buster, so a year-long Cache-Control would let a browser
serve a stale asset past the next deploy. static_v() is the only sanctioned
way to reference a file under static/ from a template.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = REPO_ROOT / "templates"

BAD_PATTERN = re.compile(r"""url_for\(\s*['"]static['"]""")


def _offenders():
    found = []
    for tpl in sorted(TEMPLATES.rglob("*.html")):
        text = tpl.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BAD_PATTERN.search(line):
                found.append(f"{tpl.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return found


def test_no_raw_url_for_static_in_templates():
    offenders = _offenders()
    assert offenders == [], (
        "Raw url_for('static', ...) has no cache-buster, which is unsafe now that "
        "SEND_FILE_MAX_AGE_DEFAULT is a year (nx_lib/__init__.py). Use static_v(...) "
        "instead:\n" + "\n".join(offenders)
    )
