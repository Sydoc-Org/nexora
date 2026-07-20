"""Reporting i18n lint: no hardcoded English reaches reporting users.

D-language (2026-07 flagship polish): every user-facing string on the
reporting surfaces goes through gettext ({{ _("...") }} in markup, the
|tojson-injected I18N constants in the JS partials) or DB-driven labels.
This lint pins the two regression classes that produced the EN/DE mix:

1. Markup text nodes with >= 2 consecutive alphabetic words outside any
   Jinja expression, in the two reporting page templates.
2. String literals fed to textContent/innerHTML/.title assignments or used
   as `|| '...'` fallbacks in the reporting JS partials (HTML tags are
   stripped first so class-attribute soup can't false-positive).

Single words (CSV, XLSX, Beta, ...) are invisible to this lint by design —
a 1-word heuristic drowns in identifiers. If a flagged literal is genuinely
non-linguistic, add it to ALLOWED with a justification; never weaken the
regexes.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

MARKUP_TEMPLATES = [
    REPO_ROOT / "templates" / "reporting.html",
    REPO_ROOT / "templates" / "_reporting_simple.html",
]
JS_PARTIALS = sorted((REPO_ROOT / "templates" / "js").glob("_reporting*.html"))

WORDS = re.compile(r"[A-Za-z]{2,}[ ]+[A-Za-z]{2,}")
JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}")
TAGS = re.compile(r"<[^>]*>")
TEXT_NODE = re.compile(r">([^<>]+)<")
JS_LITERAL = re.compile(
    r"(?:textContent|innerHTML|\.title)\s*=\s*(['\"])((?:(?!\1).)*)\1"
    r"|\|\|\s*(['\"])((?:(?!\3).)*)\3"
)

ALLOWED = {
    # 'literal': 'why it is fine' — keys must be the POST-STRIP form (the
    # walkers strip HTML tags and whitespace before the lookup). Currently
    # empty: Tasks 2-4 removed every known offender.
}


def _markup_offenders():
    found = []
    for tpl in MARKUP_TEMPLATES:
        text = JINJA.sub("", tpl.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in TEXT_NODE.finditer(line):
                node = m.group(1).strip()
                if node in ALLOWED:
                    continue
                if WORDS.search(node):
                    found.append(f"{tpl.name}:{lineno}: >{node}<")
    return found


def _js_offenders():
    found = []
    for tpl in JS_PARTIALS:
        text = JINJA.sub("", tpl.read_text(encoding="utf-8"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(("//", "*", "/*")):
                continue  # comments are developer-facing
            for m in JS_LITERAL.finditer(line):
                lit = TAGS.sub("", m.group(2) or m.group(4) or "").strip()
                if not lit or lit in ALLOWED:
                    continue
                if WORDS.search(lit):
                    found.append(f"{tpl.name}:{lineno}: '{lit}'")
    return found


def test_reporting_markup_has_no_hardcoded_english():
    offenders = _markup_offenders()
    assert offenders == [], (
        "Hardcoded multi-word text in reporting markup — wrap it in "
        '{{ _("...") }} and run the /nx-i18n cycle:\n' + "\n".join(offenders)
    )


def test_reporting_js_partials_have_no_hardcoded_english():
    offenders = _js_offenders()
    assert offenders == [], (
        "Hardcoded multi-word string literal in a reporting JS partial — "
        'inject it via an I18N constant ({{ _("...")|tojson }}) and run '
        "the /nx-i18n cycle:\n" + "\n".join(offenders)
    )
