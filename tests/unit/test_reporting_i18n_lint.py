"""Reporting i18n lint: no hardcoded English reaches reporting users.

D-language (2026-07 flagship polish): every user-facing string on the
reporting surfaces goes through gettext ({{ _("...") }} in markup, the
|tojson-injected I18N constants in the JS partials/shims) or DB-driven
labels. This lint pins the two regression classes that produced the EN/DE
mix:

1. Markup text nodes with >= 2 consecutive alphabetic words outside any
   Jinja expression, in the two reporting page templates.
2. String literals fed to textContent/innerHTML/.title assignments or used
   as `|| '...'` fallbacks, in both the reporting JS *template partials*
   (`templates/js/_reporting*.html`, which still hold inline behaviour) and
   the reporting *static shims* (`static/js/reporting*.js` — the #191
   shim-ification target: plain JS with no Jinja, translated text riding in
   via a `window.NX_I18N_*` object built by the paired shim). Same rule,
   same regex, two source trees — a page moving from the first to the
   second must not fall out of coverage. (HTML tags are stripped first so
   class-attribute soup can't false-positive.)

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
# Widened for the #191 shim-ification (beautify phase 2b, task 1): as pages
# move to static/js/<name>.js their behaviour must stay under this lint.
# Deliberately "*reporting*.js" (not just "reporting*.js"): this plan's own
# Task 5 creates static/js/generali_reporting.js (a reporting page under the
# Generali tenant prefix), which a startswith-only glob would miss. Not
# widened further than that — other #191 shims outside this reporting lint's
# scope (workitems_overview.js, admin_access_control.js,
# workitem_detail_panel.js, ...) are intentionally not covered here.
STATIC_JS_GLOB = "*reporting*.js"
STATIC_JS = sorted((REPO_ROOT / "static" / "js").glob(STATIC_JS_GLOB))

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
    # walkers strip HTML tags and whitespace before the lookup).
    #
    # --- Task 1 finding (beautify phase 2b), NOT fixed here on purpose ---
    # static/js/reporting_schema.js uses `I18N.key || '<English default>'`
    # as a defensive fallback for the case window.NX_I18N_REPORTING_SCHEMA
    # itself is missing (script loaded without its shim, or a test harness
    # that stubs `window` without it) — every key IS otherwise populated by
    # templates/js/_reporting_schema_js.html via {{ _(...)|tojson }}, so the
    # literal is unreachable on any real page today. It is a real,
    # pre-existing hardcoded-English literal per the letter of this lint's
    # rule, and per Task 1's brief it is reported here rather than patched
    # silently (patching reporting_schema.js's behaviour is outside a
    # guard-widening task). See task-1-report.md for the full finding.
    # Follow-up: fix reporting_schema.js (drop the fallback literal, or move
    # it through gettext too) and remove these entries.
    # tracked: issue #246
    "Primary key": "Task 1 finding, tracked follow-up — see issue #246",
    "References {t}": "Task 1 finding, tracked follow-up — see issue #246",
    "Nothing matches that.": "Task 1 finding, tracked follow-up — see issue #246",
    "These are the tables this source reads.": "Task 1 finding, tracked follow-up — see issue #246",
    "No foreign keys defined — showing the biggest tables.": "Task 1 finding, tracked follow-up — see issue #246",
    "Showing the {n} most connected tables.": "Task 1 finding, tracked follow-up — see issue #246",
    "Could not read this database.": "Task 1 finding, tracked follow-up — see issue #246",
    "{n} more not shown": "Task 1 finding, tracked follow-up — see issue #246",
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


def _js_offenders(files):
    """Scan a list of JS-bearing files (Jinja partials or plain .js) for
    hardcoded-English string literals, using the same rule for both."""
    found = []
    for tpl in files:
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
    offenders = _js_offenders(JS_PARTIALS)
    assert offenders == [], (
        "Hardcoded multi-word string literal in a reporting JS partial — "
        'inject it via an I18N constant ({{ _("...")|tojson }}) and run '
        "the /nx-i18n cycle:\n" + "\n".join(offenders)
    )


def test_reporting_static_js_has_no_hardcoded_english():
    """Widened coverage (#191 shim-ification, beautify phase 2b task 1):
    once a reporting page's behaviour moves to static/js/<name>.js it must
    stay just as clean as the template partial it came from."""
    offenders = _js_offenders(STATIC_JS)
    assert offenders == [], (
        "Hardcoded multi-word string literal in a reporting static/js "
        "shim — inject it via the shim's window.NX_I18N_* object "
        '({{ _("...")|tojson }} in the paired templates/js/_*_js.html) and '
        "run the /nx-i18n cycle:\n" + "\n".join(offenders)
    )


def test_static_js_glob_covers_future_shim_filenames():
    """Confirm the actual glob constant the module uses (STATIC_JS_GLOB) is
    shaped to catch the files this plan is about to create — including
    Task 5's static/js/generali_reporting.js, which does not start with
    "reporting" — not just what happens to exist today."""
    import fnmatch

    future_names = [
        "reporting_advanced.js",
        "reporting_viz.js",
        "reporting_simple_chart.js",
        "reporting_simple_library.js",
        "reporting_simple_result.js",
        "reporting_simple_wizard.js",
        "reporting_dashboard.js",
        "reporting_schema.js",
        "reporting_simple.js",
        "generali_reporting.js",
    ]
    for name in future_names:
        assert fnmatch.fnmatch(name, STATIC_JS_GLOB), name

    # and unrelated #191 shims outside this reporting-specific lint's scope
    # must NOT be swept in by the widened pattern.
    out_of_scope_names = [
        "workitems_overview.js",
        "admin_access_control.js",
        "workitem_detail_panel.js",
        "generali_crud.js",
        "nx_core.js",
    ]
    for name in out_of_scope_names:
        assert not fnmatch.fnmatch(name, STATIC_JS_GLOB), name


def test_js_offender_detection_catches_hardcoded_english(tmp_path):
    """Regression test proving the widened scan actually flags a violation
    when one is introduced into a static/js file — not just that the glob
    compiles. Two cases: a textContent assignment and an `||` fallback,
    mirroring the two sub-patterns JS_LITERAL matches."""
    bad_file = tmp_path / "reporting_totally_new.js"
    bad_file.write_text(
        "\n".join(
            [
                "(function () {",
                "  var I18N = window.NX_I18N_REPORTING_TOTALLY_NEW || {};",
                "  function render() {",
                "    el.textContent = 'This is obviously hardcoded English';",
                "    other.title = (I18N.hint || 'Also hardcoded as a fallback');",
                "  }",
                "})();",
            ]
        ),
        encoding="utf-8",
    )

    offenders = _js_offenders([bad_file])

    assert any("This is obviously hardcoded English" in o for o in offenders)
    assert any("Also hardcoded as a fallback" in o for o in offenders)


def test_js_offender_detection_ignores_translated_and_short_literals(tmp_path):
    """Sanity check the fixture harness isn't just flagging everything: a
    single word and an already-i18n'd value must NOT trip the lint."""
    good_file = tmp_path / "reporting_totally_fine.js"
    good_file.write_text(
        "\n".join(
            [
                "(function () {",
                "  var I18N = window.NX_I18N_REPORTING_TOTALLY_FINE || {};",
                "  function render() {",
                "    el.textContent = I18N.label;",
                "    other.title = I18N.hint || 'CSV';",
                "  }",
                "})();",
            ]
        ),
        encoding="utf-8",
    )

    assert _js_offenders([good_file]) == []
